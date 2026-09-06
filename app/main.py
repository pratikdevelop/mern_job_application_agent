from datetime import datetime
from fastapi import FastAPI, HTTPException
from .db import SessionLocal, init_db
from .models import CandidateProfile, Company, Job, Application
from .schemas import CompanyCreate, JobCreate
from .config import settings
from .services.ai import build_candidate_profile, score_job, generate_email
from .services.gmail import send_email

app = FastAPI(title="MERN Job Application AI Agent")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"message": "MERN Job Application AI Agent is running"}

@app.post("/profile/build")
def build_profile():
    profile = build_candidate_profile()
    db = SessionLocal()
    try:
        import json
        row = CandidateProfile(profile_json=json.dumps(profile))
        db.add(row)
        db.commit()
        return profile
    finally:
        db.close()

@app.post("/companies")
def create_company(payload: CompanyCreate):
    db = SessionLocal()
    try:
        row = Company(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "name": row.name}
    finally:
        db.close()

@app.post("/jobs")
def create_job(payload: JobCreate):
    db = SessionLocal()
    try:
        if not db.get(Company, payload.company_id):
            raise HTTPException(404, "Company not found")
        row = Job(**payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "title": row.title}
    finally:
        db.close()

@app.post("/jobs/{job_id}/score")
def score(job_id: int):
    import json
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        profile_row = db.query(CandidateProfile).order_by(CandidateProfile.id.desc()).first()
        if not job or not profile_row:
            raise HTTPException(404, "Job or candidate profile not found")
        profile = json.loads(profile_row.profile_json)
        value = score_job(profile, job.title, job.description)
        app_row = Application(job_id=job.id, match_score=value)
        db.add(app_row)
        db.commit()
        db.refresh(app_row)
        return {"application_id": app_row.id, "score": value}
    finally:
        db.close()

@app.post("/applications/{application_id}/generate-email")
def generate_application_email(application_id: int):
    import json
    db = SessionLocal()
    try:
        application = db.get(Application, application_id)
        profile_row = db.query(CandidateProfile).order_by(CandidateProfile.id.desc()).first()
        if not application or not profile_row:
            raise HTTPException(404, "Application or profile not found")
        job = db.get(Job, application.job_id)
        company = db.get(Company, job.company_id)
        profile = json.loads(profile_row.profile_json)
        email = generate_email(profile, company.name, job.title, job.description)
        application.email_subject = email["subject"]
        application.email_body = email["body"]
        application.status = "pending_approval"
        db.commit()
        return email
    finally:
        db.close()

@app.post("/applications/{application_id}/approve")
def approve(application_id: int):
    db = SessionLocal()
    try:
        application = db.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
        application.approved = True
        application.status = "approved"
        db.commit()
        return {"status": "approved"}
    finally:
        db.close()

@app.post("/applications/{application_id}/send")
def send(application_id: int):
    db = SessionLocal()
    try:
        application = db.get(Application, application_id)
        if not application:
            raise HTTPException(404, "Application not found")
        if not application.approved:
            raise HTTPException(400, "Human approval is required before sending")

        job = db.get(Job, application.job_id)
        company = db.get(Company, job.company_id)
        if not company.hr_email or not company.email_verified:
            raise HTTPException(400, "A verified HR/career email is required")

        message_id = send_email(
            company.hr_email,
            application.email_subject,
            application.email_body,
            settings.resume_path,
        )
        application.status = "sent"
        application.sent_at = datetime.utcnow()
        db.commit()
        return {"status": "sent", "message_id": message_id}
    finally:
        db.close()
