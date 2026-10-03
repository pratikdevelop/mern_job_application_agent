import csv
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

from ..config import settings
from .ai import build_candidate_profile, score_job, generate_email
from .gmail import send_email


def clean(value):
    return str(value or "").strip()


def normalize_email(value):
    return clean(value).lower()


def extract_emails(value):
    value = clean(value)
    if not value:
        return []
    parts = re.split(r"\s*[/;,]\s*", value)
    return [p.strip() for p in parts if "@" in p]


def application_key(company, email):
    return f"{clean(company).lower()}|{normalize_email(email)}"


def _first(row, *names):
    for name in names:
        value = clean(row.get(name))
        if value:
            return value
    return ""


def load_csv_jobs():
    rows = []
    for csv_file in settings.csv_file_list:
        path = Path(csv_file)
        if not path.exists():
            print(f"WARNING: CSV not found: {csv_file}")
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                company = _first(row, "Company Name")
                email_value = _first(row, "HR / Recruitment Email", "Verified HR / Recruitment Email")
                title = _first(row, "Current Opening", "MERN / Node / React Opening")
                if not title:
                    title = "MERN / Node.js / React Developer"
                description = " | ".join(
                    f"{k}: {clean(v)}" for k, v in row.items() if clean(v)
                )
                for email in extract_emails(email_value):
                    rows.append({
                        "company": company,
                        "email": email,
                        "title": title.split(";")[0].strip(),
                        "description": description,
                        "location": _first(row, "Location"),
                        "experience": _first(row, "Experience"),
                        "work_mode": _first(row, "Work Mode"),
                        "priority": _first(row, "Priority"),
                        "url": _first(row, "Careers / Opening URL"),
                        "source_csv": csv_file,
                    })
    unique = {}
    for row in rows:
        if not row["company"] or not row["email"]:
            continue
        unique.setdefault(application_key(row["company"], row["email"]), row)
    return list(unique.values())


def load_sent():
    sent = set()
    path = Path(settings.send_log_path)
    if not path.exists():
        return sent
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if clean(row.get("Status")).upper() == "SENT":
                sent.add(application_key(row.get("Company"), row.get("Email")))
    return sent


def ensure_log():
    path = Path(settings.send_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow([
                "Date", "Company", "Email", "Job Title", "Status",
                "Attempts", "Error", "Source CSV", "Score", "Reason"
            ])


def log_result(row, status, attempts=0, error="", score="", reason=""):
    ensure_log()
    with Path(settings.send_log_path).open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d"), row["company"], row["email"],
            row["title"], status, attempts, error, row["source_csv"], score, reason
        ])


def today_sent():
    path = Path(settings.send_log_path)
    if not path.exists():
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return sum(
            1 for row in csv.DictReader(f)
            if clean(row.get("Date")) == today and clean(row.get("Status")).upper() == "SENT"
        )


def build_campaign_preview():
    jobs = load_csv_jobs()
    sent = load_sent()
    profile = build_candidate_profile()
    results = []
    for job in jobs:
        key = application_key(job["company"], job["email"])
        if key in sent:
            results.append({**job, "status": "already_sent"})
            continue
        score = score_job(profile, job)
        email = None
        if score["score"] >= settings.min_score:
            email = generate_email(candidate_profile=profile, job=job, score_result=score)
        results.append({**job, "status": "ready" if email else "below_score", "score": score["score"], "reason": score["reason"], "email": email})
    return profile, results


def run_campaign(send=False, limit=None, min_score=None):
    min_score = settings.min_score if min_score is None else min_score
    limit = settings.daily_limit if limit is None else min(limit, settings.daily_limit)
    jobs = load_csv_jobs()
    sent = load_sent()
    ensure_log()
    profile = build_candidate_profile()
    print(f"Loaded {len(jobs)} unique company/email targets")
    print(f"Already sent: {len(sent)} | Sent today: {today_sent()} | Daily limit: {settings.daily_limit}")

    if not send:
        print("PREVIEW ONLY - no emails will be sent")

    sent_now = 0
    for job in jobs:
        if today_sent() >= settings.daily_limit or sent_now >= limit:
            break
        key = application_key(job["company"], job["email"])
        if key in sent:
            continue

        score = score_job(profile, job)
        print(f"\n{job['company']} <{job['email']}> | {job['title']} | score={score['score']:.0f}")
        print(f"Reason: {score['reason']}")
        if score["score"] < min_score:
            print("SKIP: below minimum score")
            continue

        email = generate_email( candidate_profile=profile,job=job,score_result=score)
        print(f"Subject: {email.get('subject', '')}")
        if not send:
            print("READY: personalized email generated; not sent")
            continue

        confirmation = input("Send this email? [y/N]: ").strip().lower()
        if confirmation != "y":
            print("SKIP: not approved")
            continue

        last_error = ""
        success = False
        attempts = 0
        for attempts in range(1, 4):
            try:
                send_email(job["email"], email["subject"], email["body"], settings.resume_path)
                success = True
                break
            except Exception as exc:
                last_error = str(exc)
                if attempts < 3:
                    time.sleep(random.randint(10, 30))

        if success:
            log_result(job, "SENT", attempts, score=score["score"], reason=score["reason"])
            sent.add(key)
            sent_now += 1
            print("SENT ✓")
            if sent_now < limit and today_sent() < settings.daily_limit:
                time.sleep(random.randint(settings.min_delay_seconds, settings.max_delay_seconds))
        else:
            log_result(job, "FAILED", attempts, last_error, score["score"], score["reason"])
            print(f"FAILED ✗ {last_error}")

    return {"sent": sent_now, "total_targets": len(jobs), "already_sent": len(sent)}
