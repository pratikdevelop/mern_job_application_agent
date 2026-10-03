from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from ..config import settings

MASTER_COLUMNS = [
    "source_platform", "source_url", "company", "job_title", "job_url",
    "description", "location", "experience", "work_mode", "priority",
    "hr_email", "hr_contact_name", "email_source_url", "email_confidence",
    "company_website", "careers_url", "current_openings", "research_status",
    "research_error", "researched_at", "imported_at",
]

ALIASES = {
    "source_platform": ["Source Platform", "Source", "Platform", "Job Source"],
    "source_url": ["Source URL", "Source Link"],
    "company": ["Company", "Company Name", "company_name", "Employer", "Organization", "Hiring Company"],
    "job_title": ["Job Title", "Title", "Current Opening", "MERN / Node / React Opening", "Position", "Job", "Job Name", "Role"],
    "job_url": ["Job URL", "Job Link", "URL", "Link", "Apply URL", "Job Posting URL", "Careers / Opening URL"],
    "description": ["Job Description", "Description", "JD", "Job Details", "Details", "Skills"],
    "location": ["Location", "Job Location", "City"],
    "experience": ["Experience", "Experience Required", "Experience Level", "Required Experience"],
    "work_mode": ["Work Mode", "Remote/Hybrid/Onsite", "Job Type", "Employment Type"],
    "priority": ["Priority"],
    "hr_email": ["HR / Recruitment Email", "Verified HR / Recruitment Email", "HR Email", "Recruiter Email", "Recruitment Email", "Contact Email", "Email"],
    "hr_contact_name": ["HR Contact Name", "Recruiter Name", "Contact Name", "HR Name"],
    "company_website": ["Company Website", "Website", "Company URL"],
}


def clean(value: object) -> str:
    return str(value or "").strip()


def first(row: dict, names: list[str]) -> str:
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def infer_platform(value: str) -> str:
    value = clean(value).lower()
    if "naukri" in value:
        return "Naukri"
    if "indeed" in value:
        return "Indeed"
    return value or "CSV Import"


def first_email(value: str) -> str:
    parts = re.split(r"[\s,;/]+", clean(value))
    return next((p for p in parts if "@" in p), "")


def normalize_row(row: dict, source_platform: str = "", source_url: str = "") -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    data = {key: first(row, [key, *names]) for key, names in ALIASES.items()}
    data.update({c: first(row, [c]) for c in MASTER_COLUMNS if c not in data})
    data["source_platform"] = infer_platform(source_platform or data.get("source_platform", ""))
    data["source_url"] = clean(source_url or data.get("source_url", ""))
    data["company"] = clean(data.get("company"))
    data["job_title"] = clean(data.get("job_title")) or "Software Developer"
    data["description"] = clean(data.get("description"))
    data["hr_email"] = first_email(data.get("hr_email", ""))
    data["research_status"] = clean(data.get("research_status")) or "pending"
    data["imported_at"] = clean(data.get("imported_at")) or now
    return {c: clean(data.get(c)) for c in MASTER_COLUMNS}


def load_master_jobs() -> list[dict]:
    path = Path(settings.master_jobs_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_master_jobs(rows: list[dict]) -> int:
    path = Path(settings.master_jobs_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize_row(row) for row in rows]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(normalized)
    return len(normalized)


def merge_rows(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str], dict] = {}
    for raw in existing + incoming:
        row = normalize_row(raw)
        if not row["company"]:
            continue
        key = (
            row["company"].lower(),
            row["job_title"].lower(),
            row["job_url"].lower(),
        )
        if key not in merged:
            merged[key] = row
            continue
        current = merged[key]
        for col in MASTER_COLUMNS:
            if not current.get(col) and row.get(col):
                current[col] = row[col]
    return list(merged.values())


def import_csv(path: str | Path, source_platform: str = "") -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    incoming: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = normalize_row(row, source_platform=source_platform)
            if item["company"]:
                incoming.append(item)
    merged = merge_rows(load_master_jobs(), incoming)
    save_master_jobs(merged)
    return {"imported_rows": len(incoming), "master_rows": len(merged), "path": settings.master_jobs_path}

def export_master_csv(output_path: str | Path | None = None) -> str:
    """Export the current master jobs CSV without modifying the original."""
    source = Path(settings.master_jobs_path)

    if not source.exists():
        raise FileNotFoundError(
            f"Master jobs file not found: {source}"
        )

    if output_path:
        destination = Path(output_path)
    else:
        export_dir = source.parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = export_dir / f"master_jobs_{timestamp}.csv"

    destination.parent.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy2(source, destination)

    return str(destination)