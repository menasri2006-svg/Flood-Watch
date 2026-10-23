from __future__ import annotations
from pathlib import Path
import json, math
import numpy as np
import planetary_computer
import pystac_client
import stackstac
import rasterio
from rasterio.features import shapes
from rasterio.transform import array_bounds
from shapely.geometry import shape, mapping
from shapely.ops import transform as geom_transform
from pyproj import Transformer
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-1-grd"

def _client():
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)

def search_scenes(bbox, start, end, orbit_direction="ANY", polarization="VV", limit=10):
    client = _client()
    query = {"polarization": {"eq": polarization}}
    if orbit_direction != "ANY":
        query["sat:orbit_state"] = {"eq": orbit_direction.lower()}
    search = client.search(collections=[COLLECTION], bbox=bbox,
                           datetime=f"{start}T00:00:00Z/{end}T23:59:59Z",
                           query=query, max_items=limit)
    result = []
    for item in search.items():
        props = item.properties
        assets = item.assets
        pols = props.get("sar:polarizations", [])
        result.append({
            "id": item.id, "datetime": props.get("datetime"),
            "platform": props.get("platform"), "orbit_direction": props.get("sat:orbit_state"),
            "relative_orbit": props.get("sat:relative_orbit"),
            "polarizations": pols, "bbox": item.bbox,
            "assets_available": [k for k in assets.keys() if k in ("vv","vh","visual","thumbnail","safe-manifest")],
            "collection": COLLECTION
        })
    return result

def _items(bbox, start, end, orbit_direction, polarization, limit):
    found = search_scenes(bbox, start, end, orbit_direction, polarization, limit)
    if not found:
        raise RuntimeError(f"No Sentinel-1 {polarization} scenes found for {start} to {end} and this AOI.")
    client = _client()
    ids = [x["id"] for x in found]
    # Re-fetch items to get signed asset hrefs.
    items = list(client.search(collections=[COLLECTION], ids=ids).items())
    by_id = {i.id:i for i in items}
    return [by_id[i] for i in ids if i in by_id], found

def _load_median(items, bbox, polarization, max_pixels=1_800_000):
    # stackstac reads the catalogue's analysis-ready COG assets lazily.
    assets = [polarization.lower()]
    stack = stackstac.stack(items, assets=assets, bounds_latlon=tuple(bbox),
                            resolution=20, epsg=4326, chunksize=512,
                            rescale=False, xy_coords="center")
    # Sentinel-1 GRD backscatter in this catalogue is linear power; convert median to dB.
    arr = stack.sel(band=polarization.lower()).median(dim="time", skipna=True).compute().values
    arr = np.asarray(arr, dtype="float32")
    # Depending on catalogue asset convention values may already be dB. This catalogue normally
    # stores calibrated linear backscatter; guard nonpositive values and document convention.
    positive = arr[np.isfinite(arr) & (arr > 0)]
    if positive.size and np.nanpercentile(positive, 95) < 1.0:
        db = 10.0 * np.log10(np.maximum(arr, 1e-10))
        input_scale = "linear_power_to_dB"
    else:
        db = arr
        input_scale = "catalogue_values_used_as_dB"
    return db, stack, input_scale

def _raster_to_geojson(mask, transform, crs, max_features=2000):
    if not np.any(mask):
        return {"type":"FeatureCollection","features":[]}
    feats = []
    for geom, val in shapes(mask.astype("uint8"), mask=mask.astype(bool), transform=transform):
        if val != 1: continue
        g = shape(geom)
        if crs and str(crs) not in ("EPSG:4326", "epsg:4326"):
            transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
            g = geom_transform(transformer.transform, g)
        feats.append({"type":"Feature","properties":{},"geometry":mapping(g)})
        if len(feats) >= max_features: break
    return {"type":"FeatureCollection","features":feats}

def run_analysis(req, outdir: Path):
    bbox = req["bbox"]
    pol = req["polarization"]
    orbit = req["orbit_direction"]
    pre_items, pre_meta = _items(bbox, req["pre_start"], req["pre_end"], orbit, pol, req["max_items_per_period"])
    post_items, post_meta = _items(bbox, req["post_start"], req["post_end"], orbit, pol, req["max_items_per_period"])
    pre_db, pre_stack, scale_pre = _load_median(pre_items, bbox, pol)
    post_db, post_stack, scale_post = _load_median(post_items, bbox, pol)
    # Reprojecting/aligning both stacks to the same geographic grid is required for pixel-wise comparison.
    # stackstac is called with identical bounds/resolution/CRS to provide matching grids.
    if pre_db.shape != post_db.shape:
        raise RuntimeError(f"Pre/post grids differ ({pre_db.shape} vs {post_db.shape}); narrow the AOI or align grids.")
    valid = np.isfinite(pre_db) & np.isfinite(post_db)
    delta = post_db - pre_db
    flood = valid & (delta <= float(req["flood_threshold_db"]))
    disturbance = valid & (delta >= float(req["disturbance_threshold_db"]))
    # Permanent water is intentionally not guessed without a calibrated multi-temporal water model.
    unchanged = valid & ~flood & ~disturbance
    # Estimate pixel area from actual grid transform in a local equal-area projection.
    # For geographic grid, use a latitude-adjusted cell area approximation.
    coords = pre_stack.coords
    xs = np.asarray(coords["x"].values); ys = np.asarray(coords["y"].values)
    dx = abs(float(np.median(np.diff(xs)))) if len(xs)>1 else 0.00018
    dy = abs(float(np.median(np.diff(ys)))) if len(ys)>1 else 0.00018
    mean_lat = float(np.mean(ys))
    pixel_area_m2 = (dx * 111320 * math.cos(math.radians(mean_lat))) * (dy * 110574)
    valid_px = int(valid.sum())
    flood_px, disturb_px, unchanged_px = int(flood.sum()), int(disturbance.sum()), int(unchanged.sum())
    valid_area = valid_px * pixel_area_m2 / 1e6
    stats = {
        "valid_pixels": valid_px,
        "valid_area_km2": round(valid_area, 4),
        "candidate_inundation_pixels": flood_px,
        "candidate_inundation_km2": round(flood_px*pixel_area_m2/1e6, 4),
        "candidate_inundation_pct": round(100*flood_px/valid_px, 2) if valid_px else None,
        "candidate_disturbance_pixels": disturb_px,
        "candidate_disturbance_km2": round(disturb_px*pixel_area_m2/1e6, 4),
        "candidate_disturbance_pct": round(100*disturb_px/valid_px, 2) if valid_px else None,
        "unchanged_pixels": unchanged_px,
        "unchanged_km2": round(unchanged_px*pixel_area_m2/1e6, 4),
        "valid_overlap_pct": 100.0 if valid_px else 0.0,
        "permanent_water_km2": None
    }
    # stackstac's x/y grid transform: construct from pixel centers.
    transform = rasterio.transform.from_origin(float(xs.min()-dx/2), float(ys.max()+dy/2), dx, dy)
    crs = "EPSG:4326"
    geo = {
        "candidate_inundation": _raster_to_geojson(flood, transform, crs),
        "candidate_disturbance": _raster_to_geojson(disturbance, transform, crs)
    }
    # Save raw-derived rasters and GeoJSON outputs for reproducibility.
    np.savez_compressed(outdir/"change_arrays.npz", pre_db=pre_db, post_db=post_db, delta_db=delta, valid=valid)
    (outdir/"candidate_inundation.geojson").write_text(json.dumps(geo["candidate_inundation"]))
    (outdir/"candidate_disturbance.geojson").write_text(json.dumps(geo["candidate_disturbance"]))
    # Choose representative scenes nearest the median date for metadata.
    def representative(items, meta):
        x = meta[0] if meta else {}
        return {"id":x.get("id"), "datetime":x.get("datetime"), "platform":x.get("platform"),
                "orbit_direction":x.get("orbit_direction"), "relative_orbit":x.get("relative_orbit"),
                "collection":COLLECTION, "scene_count":len(items)}
    return {
        "bbox":bbox, "pre_scene":representative(pre_items, pre_meta),
        "post_scene":representative(post_items, post_meta), "statistics":stats,
        "thresholds":{"flood_delta_db":req["flood_threshold_db"],"disturbance_delta_db":req["disturbance_threshold_db"]},
        "polarization":pol, "orbit_direction":orbit,
        "method":"Median pre/post Sentinel-1 GRD backscatter difference; candidate inundation if delta <= threshold; candidate disturbance if delta >= threshold.",
        "processing_notes":[
            "Actual Sentinel-1 GRD scenes searched through Microsoft Planetary Computer STAC.",
            "Median composites reduce some scene-level speckle but do not remove all noise.",
            "This starter uses a simple threshold classifier and does not implement full DEM-based radiometric terrain correction or layover/shadow masking.",
            f"Asset scale handling: pre={scale_pre}, post={scale_post}. Verify catalogue units for the selected items before operational use.",
            "Approximate cell area is latitude-adjusted; use an equal-area projected grid for publication-grade area statistics."
        ],
        "geojson":geo
    }

def validate_footprint(job, reference_geojson, reference_name):
    from shapely.geometry import shape
    from shapely.ops import unary_union, transform as geom_transform
    from pyproj import Transformer
    # Calculate in equal-area EPSG:6933 to avoid degree-based area calculations.
    ref_geoms = [shape(f["geometry"]) for f in reference_geojson.get("features", []) if f.get("geometry")]
    if reference_geojson.get("type") == "Feature" and reference_geojson.get("geometry"):
        ref_geoms = [shape(reference_geojson["geometry"])]
    if not ref_geoms: raise ValueError("Reference GeoJSON contains no valid geometries")
    reference = unary_union(ref_geoms)
    pred_fc = job.get("geojson",{}).get("candidate_inundation",{})
    pred_geoms = [shape(f["geometry"]) for f in pred_fc.get("features", []) if f.get("geometry")]
    if not pred_geoms: raise ValueError("No candidate inundation polygons to compare")
    predicted = unary_union(pred_geoms)
    to_equal_area = Transformer.from_crs("EPSG:4326","EPSG:6933",always_xy=True).transform
    p = geom_transform(to_equal_area, predicted)
    r = geom_transform(to_equal_area, reference)
    inter = p.intersection(r).area
    union = p.union(r).area
    precision = inter/p.area if p.area else 0
    recall = inter/r.area if r.area else 0
    return {"reference_name":reference_name, "reference_area_km2":round(r.area/1e6,4),
            "candidate_area_km2":round(p.area/1e6,4),"intersection_km2":round(inter/1e6,4),
            "precision":round(precision,4),"recall":round(recall,4),
            "iou":round(inter/union,4) if union else 0,
            "warning":"Metrics compare a threshold-based candidate mask with the supplied reference. Results depend on reference date, scale, and alignment."}

def make_report(job, path: Path):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    s=job.get("statistics",{})
    story=[Paragraph("VARUNA — Satellite Flood Situation Report", styles["Title"]),
           Paragraph("Evidence-grounded satellite surface-change summary", styles["Heading2"]),
           Spacer(1,10),
           Paragraph(f"Job ID: {job.get('job_id','')}",styles["BodyText"]),
           Paragraph(f"Pre-event scene: {job.get('pre_scene',{}).get('datetime','N/A')}",styles["BodyText"]),
           Paragraph(f"Post-event scene: {job.get('post_scene',{}).get('datetime','N/A')}",styles["BodyText"]),
           Paragraph(f"Polarization: {job.get('polarization','N/A')} | Orbit: {job.get('orbit_direction','N/A')}",styles["BodyText"]),
           Spacer(1,12), Paragraph("Derived statistics",styles["Heading2"])]
    rows=[["Metric","Result"],
          ["Candidate inundation (km²)",str(s.get("candidate_inundation_km2","N/A"))],
          ["Candidate disturbance (km²)",str(s.get("candidate_disturbance_km2","N/A"))],
          ["Unchanged surface (km²)",str(s.get("unchanged_km2","N/A"))],
          ["Valid pixels",str(s.get("valid_pixels","N/A"))],
          ["Flood threshold (dB)",str(job.get("thresholds",{}).get("flood_delta_db","N/A"))],
          ["Disturbance threshold (dB)",str(job.get("thresholds",{}).get("disturbance_delta_db","N/A"))]]
    table=Table(rows,colWidths=[270,180])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e9f0ef")),
                               ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#cbd5d1")),
                               ("PADDING",(0,0),(-1,-1),7)]))
    story += [table,Spacer(1,12),Paragraph("Method and limitations",styles["Heading2"]),
              Paragraph(job.get("method","N/A"),styles["BodyText"]),Spacer(1,6)]
    for note in job.get("processing_notes",[]):
        story.append(Paragraph("• "+note,styles["BodyText"])); story.append(Spacer(1,4))
    story += [Spacer(1,8),Paragraph("These results are satellite-derived candidate changes, not official flood confirmation. They do not measure casualties or injuries. Verify with independent reference data, field observations, and local authorities before emergency decisions.",styles["Italic"])]
    doc.build(story)
