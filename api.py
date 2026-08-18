import os
import uuid
import sqlite3
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from orchestrator import run_pipeline, run_batch_pipeline

app = FastAPI(title="TalentIQ — Resume Intelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = "talentiq.db"
HF_API_KEY = os.environ.get("HF_API_KEY", "")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            score INTEGER,
            grade TEXT,
            verdict TEXT,
            skills TEXT,
            matched_skills TEXT,
            missing_skills TEXT,
            summary TEXT,
            full_result TEXT,
            job_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


def save_candidate(candidate: dict, job_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO candidates
        (id, name, email, score, grade, verdict, skills, matched_skills, missing_skills, summary, full_result, job_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate.get("candidate_id", str(uuid.uuid4())),
        candidate.get("name", ""),
        candidate.get("email", ""),
        candidate.get("overall_score", 0),
        candidate.get("grade", ""),
        candidate.get("verdict", ""),
        json.dumps(candidate.get("normalized_skills", [])),
        json.dumps(candidate.get("matched_skills", [])),
        json.dumps(candidate.get("missing_skills", [])),
        candidate.get("summary", ""),
        json.dumps(candidate),
        job_id
    ))
    conn.commit()
    conn.close()


def get_candidates_for_job(job_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT full_result FROM candidates WHERE job_id=? ORDER BY score DESC", (job_id,))
    rows = c.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]


@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


@app.post("/api/v1/parse")
async def parse_single_resume(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    api_key: str = Form(default="")
):
    hf_key = api_key or HF_API_KEY
    if not hf_key:
        raise HTTPException(status_code=400, detail="HuggingFace API key required")

    allowed = [".pdf", ".docx", ".txt"]
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {suffix} not supported. Use PDF, DOCX, or TXT.")

    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{suffix}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    job_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO jobs (id, description) VALUES (?, ?)", (job_id, job_description))
    conn.commit()
    conn.close()

    result = run_pipeline(str(file_path), job_description, hf_key, file_id)

    print(f"\n[TalentIQ] Pipeline status: {result['status']}")
    if result.get('error'):
        print(f"[TalentIQ] Error: {result['error']}")
    for stage_name, stage_data in result.get('stages', {}).items():
        print(f"[TalentIQ]   {stage_name}: {stage_data.get('status', 'unknown')}")

    if result.get("final"):
        result["final"]["job_id"] = job_id
        save_candidate(result["final"], job_id)

    return {
        "success": result["status"] == "success",
        "job_id": job_id,
        "candidate": result.get("final"),
        "error": result.get("error"),
        "processing_time": result.get("processing_time_seconds")
    }


@app.post("/api/v1/parse/batch")
async def parse_batch_resumes(
    files: list[UploadFile] = File(...),
    job_description: str = Form(...),
    api_key: str = Form(default="")
):
    hf_key = api_key or HF_API_KEY
    if not hf_key:
        raise HTTPException(status_code=400, detail="HuggingFace API key required")

    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Max 20 resumes per batch")

    job_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO jobs (id, description) VALUES (?, ?)", (job_id, job_description))
    conn.commit()
    conn.close()

    file_paths = []
    for file in files:
        suffix = Path(file.filename).suffix.lower()
        file_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{file_id}{suffix}"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        file_paths.append(str(file_path))

    batch_result = run_batch_pipeline(file_paths, job_description, hf_key)

    for candidate in batch_result.get("ranked_candidates", []):
        candidate["job_id"] = job_id
        save_candidate(candidate, job_id)

    return {
        "success": True,
        "job_id": job_id,
        "total_processed": batch_result["total_processed"],
        "successful": batch_result["successful"],
        "ranked_candidates": batch_result["ranked_candidates"]
    }


@app.get("/api/v1/jobs/{job_id}/candidates")
async def get_job_candidates(job_id: str):
    candidates = get_candidates_for_job(job_id)
    if not candidates:
        raise HTTPException(status_code=404, detail="No candidates found for this job")
    return {
        "job_id": job_id,
        "total": len(candidates),
        "candidates": candidates
    }


@app.get("/api/v1/skills/taxonomy")
async def get_taxonomy():
    with open("data/taxonomy.json", "r") as f:
        taxonomy = json.load(f)
    return taxonomy


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "TalentIQ"}


app.mount("/static", StaticFiles(directory="frontend"), name="static")
