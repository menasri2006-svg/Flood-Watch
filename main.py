from __future__ import annotations
import json, os, uuid, traceback
from datetime import date
from pathlib import Path
from typing import Literal, Optional
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .satellite import search_scenes, run_analysis, validate_footprint, make_report

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "jobs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
JOBS: dict[str, dict] = {}

app = FastAPI(title="VARUNA Flood Intelligence API", version="1.0.0",
              description="Satellite-derived change detection. Results are candidates, not emergency ground truth.")
app.add_middleware(
    CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

class AnalyzeRequest(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="[minLon,minLat,maxLon,maxLat]")
    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    orbit_direction: Literal["ASCENDING", "DESCENDING", "ANY"] = "ANY"
    polarization: Literal["VV", "VH"] = "VV"
    flood_threshold_db: float = -3.5
    disturbance_threshold_db: float = 3.5
    max_items_per_period: int = Field(default=8, ge=1, le=20)

class ValidateRequest(BaseModel):
    job_id: str
    reference_geojson: dict
    reference_name: str = "User-provided independent reference"

class AskRequest(BaseModel):
    question: str
    job_id: Optional[str] = None
    language: Literal["en", "ne"] = "en"

def check_bbox(bbox):
    if len(bbox) != 4:
        raise HTTPException(400, "bbox must contain [minLon,minLat,maxLon,maxLat]")
    a,b,c,d = bbox
    if not (-180 <= a < c <= 180 and -90 <= b < d <= 90):
        raise HTTPException(400, "Invalid bounding box coordinates")
    if (c-a)*(d-b) > 4:
        raise HTTPException(400, "AOI is too large for this starter. Use a bbox under 4 square degrees.")
    return bbox

@app.get("/api/health")
def health():
    return {"status":"ok", "service":"VARUNA Flood Intelligence API"}

@app.get("/api/scenes")
def scenes(bbox: str, start: date, end: date, orbit_direction: str = "ANY",
           polarization: str = "VV", limit: int = 10):
    try:
        box = [float(v) for v in bbox.split(",")]
        check_bbox(box)
        if start > end: raise HTTPException(400, "start must be before end")
        if polarization not in ("VV", "VH"): raise HTTPException(400, "polarization must be VV or VH")
        return {"items": search_scenes(box, start.isoformat(), end.isoformat(),
                                       orbit_direction, polarization, min(max(limit,1),20))}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(502, f"STAC search failed: {str(e)[:350]}")

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    check_bbox(req.bbox)
    if req.pre_start > req.pre_end or req.post_start > req.post_end:
        raise HTTPException(400, "Each date window must have start <= end")
    if req.pre_end >= req.post_start:
        raise HTTPException(400, "Pre-event window must end before post-event window starts")
    job_id = str(uuid.uuid4())
    outdir = DATA_DIR / job_id
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_analysis(req.model_dump(mode="json"), outdir)
        result["job_id"] = job_id
        result["status"] = "completed"
        (outdir / "result.json").write_text(json.dumps(result, indent=2, default=str))
        JOBS[job_id] = result
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(502, f"Analysis could not be completed. Check acquisition availability, internet access, and backend logs. Details: {str(e)[:450]}")

@app.post("/api/validate")
def validate(req: ValidateRequest):
    job = JOBS.get(req.job_id)
    if not job:
        path = DATA_DIR / req.job_id / "result.json"
        if path.exists(): job = json.loads(path.read_text())
    if not job: raise HTTPException(404, "Analysis job not found on this server")
    try:
        result = validate_footprint(job, req.reference_geojson, req.reference_name)
        job["validation"] = result
        JOBS[req.job_id] = job
        (DATA_DIR / req.job_id / "result.json").write_text(json.dumps(job, indent=2, default=str))
        return result
    except Exception as e:
        raise HTTPException(400, f"Reference validation failed: {str(e)[:350]}")

@app.post("/api/copilot/ask")
def ask(req: AskRequest):
    q = req.question.strip()
    if not q: raise HTTPException(400, "Enter a question")
    lower = q.lower()
    if any(word in lower for word in ["casualties", "deaths", "dead", "fatalities", "missing persons", "injuries", "how many people"]):
        return {"answer":"VARUNA SCIENTIFIC DISCLOSURE: Casualties, fatalities, injuries, and missing persons cannot be determined from Sentinel-1 satellite imagery alone. This system measures satellite-observed surface changes only. Consult official disaster management authorities for verified human-impact figures.",
                "evidence":["Satellite radar measures surface backscatter, not human casualty counts."],
                "refused":True}
    job = JOBS.get(req.job_id) if req.job_id else None
    if not job and req.job_id:
        p = DATA_DIR / req.job_id / "result.json"
        if p.exists(): job = json.loads(p.read_text())
    if not job:
        return {"answer":"No completed analysis is attached to this question. Run a satellite analysis first; then ask about candidate inundation, surface disturbance, scene dates, or processing thresholds.",
                "evidence":["No job_id with a completed analysis was supplied."],"refused":False}
    stats = job.get("statistics", {})
    pre, post = job.get("pre_scene",{}), job.get("post_scene",{})
    if any(w in lower for w in ["flood", "inundat", "water"]):
        ans = f"The current threshold-based analysis identified {stats.get('candidate_inundation_km2', 'not available')} km² as candidate inundation. This is a radar-change indicator, not confirmed flood extent. Check the map, terrain effects, and independent reference data before operational use."
    elif any(w in lower for w in ["debris", "scour", "disturbance"]):
        ans = f"The analysis identified {stats.get('candidate_disturbance_km2', 'not available')} km² as candidate surface disturbance based on increased VV backscatter. This class may include non-debris changes and needs field or reference validation."
    elif any(w in lower for w in ["date", "when", "scene", "acquisition"]):
        ans = f"Pre-event scene: {pre.get('datetime', 'not available')}. Post-event scene: {post.get('datetime', 'not available')}. Always inspect acquisition timing and time lag relative to the event."
    else:
        ans = "I can answer questions about the attached analysis evidence: candidate inundation area, candidate surface disturbance, acquisition dates, thresholds, and reference-validation metrics. I will not infer casualties or facts absent from the data."
    return {"answer":ans,"evidence":[
        f"Job: {job.get('job_id','unknown')}",
        f"Pre-event: {pre.get('datetime','not available')}",
        f"Post-event: {post.get('datetime','not available')}",
        f"Classification method: {job.get('method','not available')}"
    ],"refused":False}

@app.get("/api/report/{job_id}")
def report(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        p = DATA_DIR / job_id / "result.json"
        if p.exists(): job = json.loads(p.read_text())
    if not job: raise HTTPException(404, "Analysis job not found")
    try:
        path = DATA_DIR / job_id / "situation_report.pdf"
        make_report(job, path)
        return FileResponse(path, media_type="application/pdf", filename=f"VARUNA_{job_id[:8]}_report.pdf")
    except Exception as e:
        raise HTTPException(500, f"Could not generate report: {str(e)[:250]}")
