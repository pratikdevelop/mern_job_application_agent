from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .config import settings
from .services.ai import build_candidate_profile, generate_email
from .services.campaign import load_csv_jobs, load_sent, today_sent
from .services.company_research import research_master_jobs
from .services.job_import import export_master_csv, import_csv, load_master_jobs
from .services.matching import calculate_match

app = FastAPI(
    title="MERN Job Application Agent",
    version="2.1.0",
)


class EmailPreviewRequest(BaseModel):
    job_id: int


class ResearchRequest(BaseModel):
    limit: int = 10
    force: bool = False


def _safe_job_rows() -> list[dict]:
    """Return master rows plus configured CSV jobs for the dashboard.
    Master rows may not have an HR email yet; those remain visible.
    """
    rows: list[dict] = []
    master = load_master_jobs()

    for row in master:
        rows.append(
            {
                "company": row.get("company", ""),
                "email": row.get("hr_email", ""),
                "title": row.get("job_title", ""),
                "description": row.get("description", ""),
                "location": row.get("location", ""),
                "work_mode": row.get("work_mode", ""),
                "experience": row.get("experience", ""),
                "priority": row.get("priority", ""),
                "url": row.get("job_url", ""),
                "source_csv": settings.master_jobs_path,
                "source_platform": row.get("source_platform", ""),
                "company_website": row.get("company_website", ""),
                "careers_url": row.get("careers_url", ""),
                "email_confidence": row.get("email_confidence", ""),
                "email_source_url": row.get("email_source_url", ""),
                "current_openings": row.get("current_openings", ""),
                "research_status": row.get("research_status", ""),
            }
        )

    # Also show existing configured CSV jobs, while avoiding obvious duplicates.
    existing_keys = {
        (
            row["company"].strip().lower(),
            row["title"].strip().lower(),
            row.get("url", "").strip().lower(),
        )
        for row in rows
    }

    for row in load_csv_jobs():
        key = (
            row["company"].strip().lower(),
            row["title"].strip().lower(),
            row.get("url", "").strip().lower(),
        )
        if key in existing_keys:
            continue
        rows.append(row)

    return rows


def _jobs_with_scores() -> tuple[dict, list[dict]]:
    rows = _safe_job_rows()
    sent = load_sent()
    profile = build_candidate_profile()
    items = []

    for index, job in enumerate(rows):
        match = calculate_match(
            candidate_profile=profile,
            job=job,
        )

        company = str(job.get("company", ""))
        email = str(job.get("email", ""))
        key = f"{company.strip().lower()}|{email.strip().lower()}"

        items.append(
            {
                "id": index,
                "company": company,
                "email": email,
                "title": job.get("title", ""),
                "score": match["score"],
                "recommendation": match["recommendation"],
                "reason": match["reason"],
                "matching_skills": match["matching_skills"],
                "missing_skills": match["missing_skills"],
                "location": job.get("location", ""),
                "work_mode": job.get("work_mode", ""),
                "experience": job.get("experience", ""),
                "url": job.get("url", ""),
                "source_platform": job.get("source_platform", ""),
                "company_website": job.get("company_website", ""),
                "careers_url": job.get("careers_url", ""),
                "email_confidence": job.get("email_confidence", ""),
                "email_source_url": job.get("email_source_url", ""),
                "current_openings": job.get("current_openings", ""),
                "research_status": job.get("research_status", ""),
                "already_sent": bool(email) and key in sent,
                "sendable": bool(email),
            }
        )

    return profile, items


@app.get("/", response_class=HTMLResponse)
def dashboard():
    html_path = Path(__file__).resolve().parent / "ui" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail="UI file not found.")
    return html_path.read_text(encoding="utf-8")


@app.get("/api/dashboard")
def api_dashboard():
    profile, items = _jobs_with_scores()
    items.sort(key=lambda item: item["score"], reverse=True)
    new_items = [item for item in items if not item["already_sent"]]
    return {
        "candidate": {
            "name": profile.get("name", settings.from_name),
            "role": profile.get("role", "Full Stack Developer"),
            "experience_years": profile.get("experience_years", 0),
        },
        "stats": {
            "total_targets": len(items),
            "new_targets": len(new_items),
            "today_sent": today_sent(),
            "daily_limit": settings.daily_limit,
            "min_score": settings.min_score,
            "master_jobs": len(load_master_jobs()),
        },
        "jobs": items,
    }


@app.post("/api/import-csv")
async def api_import_csv(
    file: UploadFile = File(...),
    source_platform: str = "CSV Import",
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    import_dir = Path(settings.master_jobs_path).parent / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = Path(file.filename).name.replace(" ", "_")
    saved = import_dir / f"{timestamp}_{safe_name}"
    saved.write_bytes(await file.read())

    try:
        result = import_csv(saved, source_platform=source_platform)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["saved_import"] = str(saved)
    result["message"] = (
        "CSV imported. Run research to find official company details, careers pages, "
        "public company-domain recruitment emails and current openings."
    )
    return result


@app.post("/api/research")
def api_research(request: ResearchRequest):
    if request.limit < 1 or request.limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    result = research_master_jobs(
        limit=request.limit,
        force=request.force,
    )
    return result


@app.get("/api/export-master")
def api_export_master():
    path = export_master_csv()
    return FileResponse(
        path=path,
        media_type="text/csv",
        filename=Path(path).name,
    )


@app.post("/api/email-preview")
def api_email_preview(request: EmailPreviewRequest):
    rows = _safe_job_rows()

    if request.job_id < 0 or request.job_id >= len(rows):
        raise HTTPException(status_code=404, detail="Job not found.")

    job = rows[request.job_id]
    if not str(job.get("email", "")).strip():
        raise HTTPException(
            status_code=400,
            detail="No HR/recruitment email is available for this job yet. Run research or import a contact email first.",
        )

    profile = build_candidate_profile()
    match = calculate_match(
        candidate_profile=profile,
        job=job,
    )
    email = generate_email(
        candidate_profile=profile,
        job=job,
        score_result=match,
    )

    return {
        "company": job["company"],
        "email": job["email"],
        "title": job["title"],
        "score": match["score"],
        "match": match,
        "subject": email["subject"],
        "body": email["body"],
    }
