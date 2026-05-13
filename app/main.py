import asyncio
import os
import time
import tempfile
import shutil
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .zip_renamer import process_container_zip, RenameInput


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, "").strip())
        return v if v > 0 else default
    except Exception:
        return default


MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 200 * 1024 * 1024)  # 200MB
MAX_ACTIVE_JOBS = _env_int("MAX_ACTIVE_JOBS", 8)                    # per worker
QUEUE_WAIT_SECONDS = _env_int("QUEUE_WAIT_SECONDS", 20)

app = FastAPI(title="Ultra-Fast ZIP Batch Renamer", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

# per-worker queue limit
_job_semaphore = asyncio.Semaphore(MAX_ACTIVE_JOBS)


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/usage")
def usage():
    return FileResponse("static/usage.html")


def _rm_tree(path: str) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


async def _save_upload_to_disk(upload: UploadFile, dst_path: str) -> int:
    """
    Read uploaded file in chunks and write to disk (low RAM).
    """
    size = 0
    chunk_size = 1024 * 1024  # 1MB
    try:
        with open(dst_path, "wb") as f:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload too large (max 200 MB).")
                f.write(chunk)
    finally:
        try:
            await upload.close()
        except Exception:
            pass
    return size


@app.post("/api/rename")
async def rename_zip(
    background: BackgroundTasks,
    container_zip: UploadFile = File(...),
    exam: str = Form(...),
    city: str = Form(...),
    center: str = Form(...),
    tech: str = Form(...),
    server_number: str = Form(...),  # REQUIRED 2 digits
    date_format: str = Form(...),    # DD-MM-YYYY or MM-DD-YYYY
):
    acquired = False
    tmp_dir = tempfile.mkdtemp(prefix="zipren_")
    in_path = os.path.join(tmp_dir, "input.zip")
    out_path = os.path.join(tmp_dir, "output.zip")

    try:
        # busy queue
        try:
            await asyncio.wait_for(_job_semaphore.acquire(), timeout=QUEUE_WAIT_SECONDS)
            acquired = True
        except asyncio.TimeoutError:
            raise HTTPException(status_code=429, detail="Server busy. Please retry in a few seconds.")

        await _save_upload_to_disk(container_zip, in_path)

        # validate zip
        if not zipfile.is_zipfile(in_path):
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP.")

        meta = RenameInput(
            exam=exam,
            city=city,
            center=center,
            tech=tech,
            server_number=server_number,
            date_format=date_format,
        )

        # run processing in background thread (keeps async server responsive)
        try:
            result = await asyncio.to_thread(process_container_zip, in_path, out_path, meta)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Corrupt ZIP file.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}")

        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_exam = "".join([c for c in exam.upper() if c.isalnum() or c in ("_", "-", " ")])[:30].strip()
        download_name = f"RENAMED_{safe_exam}_{ts}.zip".replace(" ", "_")

        # cleanup after response is sent
        background.add_task(_rm_tree, tmp_dir)

        # release queue slot after processing (not waiting for download)
        _job_semaphore.release()
        acquired = False

        return FileResponse(
            out_path,
            media_type="application/zip",
            filename=download_name,
            background=background,
            headers={
                "X-Processed": str(result.processed),
                "X-Skipped": str(result.skipped),
                "X-Warnings": str(len(result.warnings)),
            },
        )

    except HTTPException:
        _rm_tree(tmp_dir)
        raise
    except Exception:
        _rm_tree(tmp_dir)
        raise HTTPException(status_code=500, detail="Unexpected server error.")
    finally:
        if acquired:
            try:
                _job_semaphore.release()
            except Exception:
                pass