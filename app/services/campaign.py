import csv
import random
import re
import time
from datetime import datetime
from pathlib import Path

from ..config import settings
from .ai import build_candidate_profile, generate_email
from .gmail import send_email
from .matching import calculate_match
from .job_import import load_master_jobs


def clean(value):
    return str(value or "").strip()


def normalize_email(value):
    return clean(value).lower()


def extract_emails(value):
    value = clean(value)

    if not value:
        return []

    parts = re.split(
        r"\s*[/;,]\s*",
        value,
    )

    return [
        part.strip()
        for part in parts
        if "@" in part
    ]


def application_key(company, email):
    return (
        f"{clean(company).lower()}|"
        f"{normalize_email(email)}"
    )


def _first(row, *names):
    for name in names:
        value = clean(row.get(name))

        if value:
            return value

    return ""


def load_csv_jobs():
    rows = []

    def add_row(row, source_csv):
        company = _first(
            row,
            "Company Name",
            "Company",
            "company_name",
            "company",
            "Employer",
        )

        email_value = _first(
            row,
            "HR / Recruitment Email",
            "Verified HR / Recruitment Email",
            "hr_email",
            "HR Email",
            "Recruiter Email",
            "Recruitment Email",
            "Contact Email",
            "Email",
        )

        title = _first(
            row,
            "Current Opening",
            "MERN / Node / React Opening",
            "job_title",
            "Job Title",
            "Title",
            "Position",
            "Role",
        ) or "MERN / Node.js / React Developer"

        description = _first(
            row,
            "Job Description",
            "description",
            "Description",
            "JD",
            "Job Details",
        )

        if not description:
            description = " | ".join(
                f"{key}: {clean(value)}"
                for key, value in row.items()
                if clean(value)
            )

        for email in extract_emails(email_value):
            rows.append(
                {
                    "company": company,
                    "email": email,
                    "title": title.split(";")[0].strip(),
                    "description": description,
                    "location": _first(row, "Location", "Job Location", "City"),
                    "experience": _first(row, "Experience", "Experience Required", "Experience Level"),
                    "work_mode": _first(row, "Work Mode", "Remote/Hybrid/Onsite", "Job Type"),
                    "priority": _first(row, "Priority"),
                    "url": _first(row, "Careers / Opening URL", "Job URL", "Job Link", "URL", "Link", "Apply URL"),
                    "source_csv": source_csv,
                    "source_platform": _first(row, "Source Platform", "Source", "Platform"),
                    "company_website": _first(row, "Company Website", "Website", "Company URL"),
                    "careers_url": _first(row, "Careers URL", "Careers Page"),
                    "email_confidence": _first(row, "Email Confidence"),
                }
            )

    # Original configured CSV sources.
    for csv_file in settings.csv_file_list:
        path = Path(csv_file)
        if not path.exists():
            print(f"WARNING: CSV not found: {csv_file}")
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                add_row(row, csv_file)

    # Imported + researched jobs. These are the jobs from the UI upload flow.
    for row in load_master_jobs():
        add_row(row, settings.master_jobs_path)

    unique = {}
    for row in rows:
        if not row["company"] or not row["email"]:
            continue
        # Same company/email should be one application target. Prefer the
        # researched/master row when one exists.
        key = application_key(row["company"], row["email"])
        if key not in unique or row.get("source_csv") == settings.master_jobs_path:
            unique[key] = row

    return list(unique.values())

def load_sent():
    sent = set()
    path = Path(settings.send_log_path)

    if not path.exists():
        return sent

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        for row in csv.DictReader(f):
            if (
                clean(
                    row.get("Status")
                ).upper()
                == "SENT"
            ):
                sent.add(
                    application_key(
                        row.get("Company"),
                        row.get("Email"),
                    )
                )

    return sent


def ensure_log():
    path = Path(settings.send_log_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not path.exists():
        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            csv.writer(f).writerow(
                [
                    "Date",
                    "Company",
                    "Email",
                    "Job Title",
                    "Status",
                    "Attempts",
                    "Error",
                    "Source CSV",
                    "Score",
                    "Reason",
                ]
            )


def log_result(
    row,
    status,
    attempts=0,
    error="",
    score="",
    reason="",
):
    ensure_log()

    with Path(
        settings.send_log_path
    ).open(
        "a",
        encoding="utf-8",
        newline="",
    ) as f:
        csv.writer(f).writerow(
            [
                datetime.now().strftime(
                    "%Y-%m-%d"
                ),
                row["company"],
                row["email"],
                row["title"],
                status,
                attempts,
                error,
                row["source_csv"],
                score,
                reason,
            ]
        )


def today_sent():
    path = Path(settings.send_log_path)

    if not path.exists():
        return 0

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        return sum(
            1
            for row in csv.DictReader(f)
            if clean(
                row.get("Date")
            ) == today
            and clean(
                row.get("Status")
            ).upper()
            == "SENT"
        )


def build_campaign_preview():
    jobs = load_csv_jobs()
    sent = load_sent()
    profile = build_candidate_profile()
    results = []

    for job in jobs:
        key = application_key(
            job["company"],
            job["email"],
        )

        if key in sent:
            results.append(
                {
                    **job,
                    "status": "already_sent",
                }
            )
            continue

        score = calculate_match(
            candidate_profile=profile,
            job=job,
        )

        email = None

        if (
            score["score"]
            >= settings.min_score
        ):
            email = generate_email(
                candidate_profile=profile,
                job=job,
                score_result=score,
            )

        results.append(
            {
                **job,
                "status": (
                    "ready"
                    if email
                    else "below_score"
                ),
                **score,
                "email": email,
            }
        )

    return profile, results


def run_campaign(
    send=False,
    limit=None,
    min_score=None,
):
    min_score = (
        settings.min_score
        if min_score is None
        else min_score
    )

    limit = (
        settings.daily_limit
        if limit is None
        else min(
            limit,
            settings.daily_limit,
        )
    )

    jobs = load_csv_jobs()
    sent = load_sent()

    ensure_log()

    profile = build_candidate_profile()

    print(
        f"Loaded {len(jobs)} unique "
        "company/email targets"
    )

    print(
        f"Already sent: {len(sent)} | "
        f"Sent today: {today_sent()} | "
        f"Daily limit: {settings.daily_limit}"
    )

    if not send:
        print(
            "PREVIEW ONLY - no emails "
            "will be sent"
        )

    sent_now = 0

    for job in jobs:
        if (
            today_sent()
            >= settings.daily_limit
            or sent_now >= limit
        ):
            break

        key = application_key(
            job["company"],
            job["email"],
        )

        if key in sent:
            continue

        score = calculate_match(
            candidate_profile=profile,
            job=job,
        )

        print(
            f"\n{job['company']} "
            f"<{job['email']}> | "
            f"{job['title']} | "
            f"score={score['score']:.0f}"
        )

        print(
            f"Reason: {score['reason']}"
        )

        if score["matching_skills"]:
            print(
                "Matching skills: "
                + ", ".join(
                    score["matching_skills"]
                )
            )

        if score["missing_skills"]:
            print(
                "Missing skills: "
                + ", ".join(
                    score["missing_skills"]
                )
            )

        print(
            f"Recommendation: "
            f"{score['recommendation']}"
        )

        if score["score"] < min_score:
            print(
                "SKIP: below minimum score"
            )
            continue

        email = generate_email(
            candidate_profile=profile,
            job=job,
            score_result=score,
        )

        print(
            f"Subject: "
            f"{email.get('subject', '')}"
        )

        if not send:
            print("\n" + "-" * 72)
            print("EMAIL PREVIEW")
            print("-" * 72)
            print(
                str(
                    email.get("body")
                    or ""
                ).strip()
            )
            print("-" * 72)
            print(
                "READY: personalized email "
                "generated; not sent"
            )
            continue

        print("\n" + "-" * 72)
        print("EMAIL PREVIEW")
        print("-" * 72)
        print(
            str(
                email.get("body")
                or ""
            ).strip()
        )
        print("-" * 72)

        confirmation = input(
            "Send this email? [y/N]: "
        ).strip().lower()

        if confirmation != "y":
            print("SKIP: not approved")
            continue

        last_error = ""
        success = False
        attempts = 0

        for attempts in range(1, 4):
            try:
                send_email(
                    job["email"],
                    email["subject"],
                    email["body"],
                    settings.resume_path,
                )

                success = True
                break

            except Exception as exc:
                last_error = str(exc)

                if attempts < 3:
                    print(
                        f"Send failed "
                        f"(attempt {attempts}/3). "
                        "Retrying..."
                    )
                    time.sleep(
                        random.randint(
                            10,
                            30,
                        )
                    )

        if success:
            log_result(
                job,
                "SENT",
                attempts,
                score=score["score"],
                reason=score["reason"],
            )

            sent.add(key)
            sent_now += 1

            print("SENT ✓")

            if (
                sent_now < limit
                and today_sent()
                < settings.daily_limit
            ):
                delay = random.randint(
                    settings.min_delay_seconds,
                    settings.max_delay_seconds,
                )

                print(
                    f"Waiting {delay} seconds "
                    "before the next email..."
                )

                time.sleep(delay)

        else:
            log_result(
                job,
                "FAILED",
                attempts,
                last_error,
                score["score"],
                score["reason"],
            )

            print(
                f"FAILED ✗ {last_error}"
            )

    return {
        "sent": sent_now,
        "total_targets": len(jobs),
        "already_sent": len(sent),
    }
