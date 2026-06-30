"""
CandidateTransformer API
========================
FastAPI application exposing the transformer pipeline via REST.
"""

import io
import csv
import json
import asyncio
from typing import Optional, Any

import httpx
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Try to import PDF/DOCX extractors gracefully
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document as DocxDoc
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

from app.core.transformer import CandidateTransformer


# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

app = FastAPI(
    title="CandidateTransformer API",
    description="Ingests multi-source candidate data and returns one canonical profile.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

transformer = CandidateTransformer()


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

GITHUB_API = "https://api.github.com"

async def fetch_github_profile(username_or_url: str) -> dict:
    """Fetch GitHub user data + top repos from public API."""
    username = username_or_url.rstrip("/").split("/")[-1]
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            user_r = await client.get(
                f"{GITHUB_API}/users/{username}",
                headers={"Accept": "application/vnd.github+json"},
            )
            user_r.raise_for_status()
            user_data: dict = user_r.json()

            repos_r = await client.get(
                f"{GITHUB_API}/users/{username}/repos",
                params={"sort": "stars", "per_page": 10},
                headers={"Accept": "application/vnd.github+json"},
            )
            repos_r.raise_for_status()
            user_data["repos"] = repos_r.json()
            return user_data
        except Exception as e:
            return {"error": str(e)}


def extract_text_from_pdf(file_bytes: bytes) -> str:
    if not HAS_PDF:
        return ""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    texts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            texts.append(t)
    return "\n".join(texts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    if not HAS_DOCX:
        return ""
    doc = DocxDoc(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_csv_row(content: str) -> Optional[dict]:
    """Parse first data row of CSV string into a dict."""
    try:
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            return dict(row)
    except Exception:
        return None


# ──────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────

class TransformRequest(BaseModel):
    csv_row: Optional[dict[str, Any]] = None
    ats_blob: Optional[dict[str, Any]] = None
    github_url: Optional[str] = None
    github_data: Optional[dict[str, Any]] = None   # pre-fetched data (for testing)
    resume_text: Optional[str] = None
    recruiter_notes: Optional[str] = None


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "CandidateTransformer"}


@app.post("/transform/json", summary="Transform from JSON inputs")
async def transform_json(req: TransformRequest):
    """
    Accept all sources as JSON. Optionally fetches GitHub live if github_url is given.
    """
    github_data = req.github_data
    if req.github_url and not github_data:
        github_data = await fetch_github_profile(req.github_url)

    try:
        profile = transformer.transform(
            csv_row=req.csv_row,
            ats_blob=req.ats_blob,
            github_data=github_data,
            resume_text=req.resume_text,
            recruiter_notes=req.recruiter_notes,
        )
        return JSONResponse(content=profile.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transform/multipart", summary="Transform with file uploads")
async def transform_multipart(
    csv_file: Optional[UploadFile] = File(None),
    ats_json: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    resume_file: Optional[UploadFile] = File(None),
    recruiter_notes: Optional[str] = Form(None),
):
    """
    Accept CSV and resume files via multipart form alongside JSON strings and URLs.
    """
    csv_row: Optional[dict] = None
    if csv_file:
        content = (await csv_file.read()).decode("utf-8", errors="replace")
        csv_row = parse_csv_row(content)

    ats_blob: Optional[dict] = None
    if ats_json:
        try:
            ats_blob = json.loads(ats_json)
        except Exception:
            raise HTTPException(status_code=400, detail="ats_json is not valid JSON")

    resume_text: Optional[str] = None
    if resume_file:
        file_bytes = await resume_file.read()
        fname = (resume_file.filename or "").lower()
        if fname.endswith(".pdf"):
            resume_text = extract_text_from_pdf(file_bytes)
        elif fname.endswith(".docx"):
            resume_text = extract_text_from_docx(file_bytes)
        else:
            resume_text = file_bytes.decode("utf-8", errors="replace")

    github_data: Optional[dict] = None
    if github_url:
        github_data = await fetch_github_profile(github_url)

    try:
        profile = transformer.transform(
            csv_row=csv_row,
            ats_blob=ats_blob,
            github_data=github_data,
            resume_text=resume_text,
            recruiter_notes=recruiter_notes,
        )
        return JSONResponse(content=profile.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transform/batch", summary="Transform multiple candidates")
async def transform_batch(requests: list[TransformRequest]):
    """Batch-process up to 50 candidates in parallel."""
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Batch limit is 50 candidates.")

    async def process_one(req: TransformRequest) -> dict:
        github_data = req.github_data
        if req.github_url and not github_data:
            github_data = await fetch_github_profile(req.github_url)
        profile = transformer.transform(
            csv_row=req.csv_row,
            ats_blob=req.ats_blob,
            github_data=github_data,
            resume_text=req.resume_text,
            recruiter_notes=req.recruiter_notes,
        )
        return profile.to_dict()

    results = await asyncio.gather(*[process_one(r) for r in requests])
    return JSONResponse(content={"count": len(results), "profiles": list(results)})
