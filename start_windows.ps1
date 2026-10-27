# One-click setup and start on Windows (PowerShell)
Set-Location $PSScriptRoot 

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creating virtual environment...' -ForegroundColor Cyan
    try { py -3 -m venv .venv } catch { python -m venv .venv }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\pip.exe install -r requirements.txt
}

if (-not (Test-Path 'models\clinical_random_forest.joblib')) {
    Write-Host 'Running the pipeline (about 2 minutes)...' -ForegroundColor Cyan
    & .\.venv\Scripts\python.exe run_pipeline.py
}

# Point the Power BI project at this folder's powerbi\data\
& .\.venv\Scripts\python.exe -m src.powerbi_project --set-data-folder

Write-Host ''
Write-Host 'Power BI: open powerbi\MumbaiHealth.pbip in Power BI Desktop, click Refresh, then Publish (see powerbi\POWERBI_GUIDE.md).' -ForegroundColor Yellow
Write-Host 'Open http://localhost:8050/            (landing page)' -ForegroundColor Green
Write-Host '     http://localhost:8050/dashboard/  (dashboard)' -ForegroundColor Green
Write-Host '     http://localhost:8050/api/docs    (FastAPI Swagger docs)' -ForegroundColor Green
Write-Host 'Press Ctrl+C to stop.' -ForegroundColor Gray

& .\.venv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port 8050
