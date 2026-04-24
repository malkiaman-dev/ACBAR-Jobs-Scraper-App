import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import zipfile


ROOT_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT_DIR / "jobs"
SCRAPER_PATH = ROOT_DIR / "scraper" / "acbar.py"
DOWNLOAD_ROOT = ROOT_DIR / "downloads_acbar_all"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

COUNTER_FILE = JOBS_DIR / ".job_counter.txt"  # never reuse numbers


app = FastAPI(title="ACBAR Vehicle Tender Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartJobRequest(BaseModel):
    pages: str = "all"          # "all" or "5"
    headless: bool = False      # set True for real server
    download: bool = True       # downloads attachments
    slow: float = 0.3           # visual slow motion
    chromedriver: str = ""      # optional explicit path


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def status_path(job_id: str) -> Path:
    return job_dir(job_id) / "status.json"


def control_path(job_id: str) -> Path:
    return job_dir(job_id) / "control.json"


def csv_path(job_id: str) -> Path:
    return job_dir(job_id) / "acbar_vehicle_tenders.csv"


def read_counter() -> int:
    if not COUNTER_FILE.exists():
        return 0
    try:
        return int(COUNTER_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def write_counter(n: int) -> None:
    COUNTER_FILE.write_text(str(n), encoding="utf-8")


def next_job_id() -> str:
    """
    sequential job id: 01_YYYY-MM-DD, 02_YYYY-MM-DD...
    Never reuses numbers even if user deletes CSV/folders.
    """
    last = read_counter()
    nxt = last + 1
    write_counter(nxt)
    date_part = datetime.now().strftime("%Y-%m-%d")
    return f"{nxt:02d}_{date_part}"


def write_control(job_id: str, pause: bool = False, stop: bool = False) -> None:
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)
    payload = {"pause": pause, "stop": stop}
    control_path(job_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_control(job_id: str) -> Dict[str, bool]:
    cp = control_path(job_id)
    if not cp.exists():
        return {"pause": False, "stop": False}
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        return {"pause": bool(data.get("pause")), "stop": bool(data.get("stop"))}
    except Exception:
        return {"pause": False, "stop": False}


@app.get("/")
def root():
    return {"ok": True, "service": "ACBAR Vehicle Tender Scraper API"}


@app.post("/jobs/start")
def start_job(req: StartJobRequest):
    job_id = next_job_id()
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)

    # control defaults
    write_control(job_id, pause=False, stop=False)

    cmd = [
        "python",
        str(SCRAPER_PATH),
        "--job-id", job_id,
        "--pages", req.pages,
        "--slow", str(req.slow),
    ]

    if req.headless:
        cmd.append("--headless")
        cmd.append("--no-visual")

    if req.download:
        cmd.append("--download")

    if req.chromedriver.strip():
        cmd += ["--chromedriver", req.chromedriver.strip()]

    # -------------------------------
    # FIX: do NOT open CMD window
    # -------------------------------
    creationflags = 0
    startupinfo = None

    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )

    return {"job_id": job_id}


@app.get("/jobs/{job_id}/status")
def get_status(job_id: str):
    sp = status_path(job_id)
    if not sp.exists():
        raise HTTPException(status_code=404, detail="Job not found or not started yet")
    with open(sp, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/jobs/{job_id}/tenders")
def list_tenders(job_id: str):
    cp = csv_path(job_id)
    if not cp.exists():
        return {"job_id": job_id, "tenders": []}

    tenders: List[Dict[str, Any]] = []
    with open(cp, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tenders.append(row)
    return {"job_id": job_id, "tenders": tenders}


# ---------------------------
# Pause / Resume / Stop
# ---------------------------

@app.post("/jobs/{job_id}/pause")
def pause_job(job_id: str):
    if not job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    c = read_control(job_id)
    write_control(job_id, pause=True, stop=bool(c.get("stop")))
    return {"job_id": job_id, "paused": True}


@app.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):
    if not job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    c = read_control(job_id)
    write_control(job_id, pause=False, stop=bool(c.get("stop")))
    return {"job_id": job_id, "paused": False}


@app.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    if not job_dir(job_id).exists():
        raise HTTPException(status_code=404, detail="Job not found")
    c = read_control(job_id)
    write_control(job_id, pause=bool(c.get("pause")), stop=True)
    return {"job_id": job_id, "stopping": True}


@app.get("/tenders/{tender_id}/download_zip")
def download_zip(tender_id: str):
    folder = DOWNLOAD_ROOT / tender_id
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Tender folder not found")

    zip_path = folder.with_suffix(".zip")
    if zip_path.exists():
        try:
            zip_path.unlink()
        except Exception:
            pass

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in folder.glob("*"):
            if p.is_file():
                z.write(p, arcname=p.name)

    return FileResponse(
        path=str(zip_path),
        filename=f"{tender_id}.zip",
        media_type="application/zip",
    )
