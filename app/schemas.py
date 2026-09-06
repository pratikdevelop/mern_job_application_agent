from pydantic import BaseModel, EmailStr, Field

class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    location: str | None = "Ujjain, Madhya Pradesh"
    hr_email: EmailStr | None = None
    email_verified: bool = False
    source_url: str | None = None

class JobCreate(BaseModel):
    company_id: int
    title: str
    description: str
    url: str | None = None

class ProfileOut(BaseModel):
    profile: dict

class EmailOut(BaseModel):
    subject: str
    body: str

class ScoreOut(BaseModel):
    application_id: int
    score: float
