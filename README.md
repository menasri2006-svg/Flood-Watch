# VARUNA — Satellite Flood Detection & Situation-Report Copilot

A full-stack starter application inspired by the supplied dashboard screenshots.

## Stack
- Frontend: React + Vite + TypeScript + Leaflet
- Backend: FastAPI + pystac-client + Planetary Computer + stackstac/xarray + rasterio + GeoPandas
- Real data: Sentinel-1 GRD observations discovered through Microsoft Planetary Computer STAC
- Outputs: scene metadata, raster-derived change statistics, GeoJSON footprints, evidence-grounded Q&A, PDF report

## Important scientific limitations
- The application uses actual Sentinel-1 acquisitions; results depend on availability and the selected AOI/date window.
- The default threshold classifier identifies *candidate* inundation and *candidate* surface disturbance from VV backscatter change. It is not a validated flood model and can confuse water, vegetation, terrain/shadow, agriculture, and other changes.
- Production processing should include orbit-file handling, precise co-registration, radiometric terrain correction, DEM-based layover/shadow masking, incidence-angle normalization, and local calibration.
- Optical/reference validation is only meaningful when an independently sourced reference footprint is uploaded or configured. The app does not invent validation scores.
- SAR imagery cannot determine casualties or deaths. The copilot explicitly refuses unsupported casualty questions.
- Demo UI values are not presented as real analysis. Empty values are shown until a successful job returns results.

## Requirements
- Python 3.11 recommended
- Node.js 20+
- Internet connection for STAC search and satellite asset access
- Enough RAM/disk for raster stacks (start with a small AOI)

## Start backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
API docs: http://127.0.0.1:8000/docs

## Start frontend
Open a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints (usually http://localhost:5173).

## Run an analysis
1. Open the app.
2. Set an area of interest (AOI) bounding box and pre/post date windows.
3. Search for available scenes first.
4. Run the analysis. Use a small AOI (for example 0.1° × 0.1°) while testing.
5. Inspect map layers, statistics, and acquisition metadata.
6. To validate, provide an independent reference footprint as GeoJSON through the API endpoint documented below.

## API endpoints
- `GET /api/health`
- `GET /api/scenes?bbox=minLon,minLat,maxLon,maxLat&start=YYYY-MM-DD&end=YYYY-MM-DD`
- `POST /api/analyze`
- `POST /api/validate`
- `POST /api/copilot/ask`
- `GET /api/report/{job_id}`

### Analyze request example
```json
{
  "bbox": [85.5, 27.7, 85.8, 28.0],
  "pre_start": "2026-08-01",
  "pre_end": "2026-08-25",
  "post_start": "2026-08-26",
  "post_end": "2026-09-10",
  "orbit_direction": "DESCENDING",
  "polarization": "VV",
  "flood_threshold_db": -3.5,
  "disturbance_threshold_db": 3.5
}
```
Use a real AOI and dates relevant to your event. These dates are examples only.

### Validation
`POST /api/validate` expects:
```json
{
  "job_id": "returned-job-id",
  "reference_geojson": { "type": "FeatureCollection", "features": [] }
}
```
Use an actual independently sourced reference footprint. Metrics compare the model's candidate inundation mask with that reference; document the reference source and date in your report.

## Data handling
This starter writes analysis outputs to `backend/data/jobs/`. Do not expose that directory publicly in production. Add authentication, rate limits, background task queue, storage quotas, and per-user job isolation before deployment.
