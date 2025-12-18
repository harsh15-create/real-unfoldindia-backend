@echo off
echo Starting Unfold India Voyage Backend...
cd backend

echo Installing dependencies...
python -m pip install -r requirements.txt

echo Starting Server...
python -m uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

pause
