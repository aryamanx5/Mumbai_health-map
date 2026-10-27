@echo off
REM One-click setup and start on Windows. Run from the project folder (double-click or "start_windows.bat").
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
if not exist models\clinical_random_forest.joblib (
  echo Running the pipeline - about 2 minutes...
  .venv\Scripts\python run_pipeline.py
)
REM Point the Power BI project at this folder's powerbi\data\ (keeps any edits made in Power BI Desktop).
.venv\Scripts\python -m src.powerbi_project --set-data-folder
echo.
echo Power BI: open powerbi\MumbaiHealth.pbip in Power BI Desktop, click Refresh, then Publish (see powerbi\POWERBI_GUIDE.md).
echo Open http://localhost:8050/            (landing page)
echo      http://localhost:8050/dashboard/  (dashboard)
echo      http://localhost:8050/api/docs    (FastAPI Swagger docs)
echo Press Ctrl+C to stop.
.venv\Scripts\uvicorn backend.main:app --host 127.0.0.1 --port 8050
