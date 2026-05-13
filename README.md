# Ultra-Fast ZIP Batch Renamer

## Rules
- Upload ONE container ZIP (max 200 MB)
- Only inner *.zip files are processed; other files are skipped
- Required fields: Exam, City, Center, Tech
- Server Number REQUIRED: exactly 2 digits (01..99)
- MAIN/BACKUP detected from filename:
  - TCMAINSVR / TCMAIN -> M
  - TCBACKUPSVR / TCBACKUP -> B
- Any digits inside filename like SVR02/SVR03 are ignored completely
- Date format selected by user: DD-MM-YYYY or MM-DD-YYYY
- Output ZIP uses ZIP_STORED (no recompression) and streaming copy (fast)

## Output
EXAM_CITY_CENTER_TECH_{M|B}{SERVER_NUMBER}_DATE.zip

Inside output ZIP:
ULTRA_FAST_ZIP_BATCH_RENAMER_LOG.txt

## Local Run (VSCode)
```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

deactivate

pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Open:
http://127.0.0.1:8000

Health check:
http://127.0.0.1:8000/healthz