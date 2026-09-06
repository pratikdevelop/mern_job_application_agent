# app/services/ai.py

from __future__ import annotations

import json
import re
from typing import Any, List

from google import genai
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services.resume import extract_resume_text


# ============================================================
# Gemini Configuration
# ============================================================

GEMINI_API_KEY = getattr(settings, "gemini_api_key", "") or ""

GEMINI_MODEL = (
    getattr(settings, "gemini_model", "")
    or "gemini-3.5-flash-lite"
)

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing. "
        "Add GEMINI_API_KEY=your_key to your .env file."
    )

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# Pydantic Schemas
# ============================================================

class ContactInfo(BaseModel):
    email: str = ""
    phone: str = ""


class CandidateProfile(BaseModel):
    name: str = ""
    role: str = "Full Stack Developer"
    experience_years: float = 0.0

    primary_skills: List[str] = Field(default_factory=list)
    secondary_skills: List[str] = Field(default_factory=list)

    education: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)

    contact: ContactInfo = Field(default_factory=ContactInfo)

    linkedin_url: str = ""
    summary: str = ""


class JobScore(BaseModel):
    score: float = Field(
        description="Candidate-job match score from 0 to 100."
    )

    reason: str = Field(
        description="Short explanation of why the candidate matches."
    )

    matching_skills: List[str] = Field(
        default_factory=list,
        description="Skills from the candidate that match the job."
    )

    missing_skills: List[str] = Field(
        default_factory=list,
        description="Important job skills the candidate appears to lack."
    )

    recommendation: str = Field(
        description="One of: apply, consider, skip."
    )


class JobEmail(BaseModel):
    subject: str = Field(
        description="Professional personalized email subject."
    )

    body: str = Field(
        description="Professional personalized job application email."
    )


# ============================================================
# Helper Functions
# ============================================================

def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    except Exception:
        return json.dumps(
            str(value),
            ensure_ascii=False,
        )


def _extract_output_text(interaction: Any) -> str:
    """
    Extract text from Gemini Interactions API response.
    """

    output_text = getattr(interaction, "output_text", None)

    if output_text:
        return str(output_text).strip()

    outputs = getattr(interaction, "outputs", None)

    if outputs:
        parts: list[str] = []

        for output in outputs:
            text = getattr(output, "text", None)

            if text:
                parts.append(str(text))

            content = getattr(output, "content", None)

            if content:
                for item in content:
                    item_text = getattr(item, "text", None)

                    if item_text:
                        parts.append(str(item_text))

        if parts:
            return "\n".join(parts).strip()

    raise RuntimeError(
        "Gemini returned no text output."
    )


def _generate_structured(
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """
    Call Gemini Interactions API and validate the response
    using Pydantic.
    """

    try:
        interaction = client.interactions.create(
            model=GEMINI_MODEL,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema.model_json_schema(),
            },
        )

    except Exception as exc:
        raise RuntimeError(
            f"Gemini API request failed using model "
            f"'{GEMINI_MODEL}': {exc}"
        ) from exc

    output_text = _extract_output_text(interaction)

    if not output_text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    output_text = output_text.strip()

    # Remove accidental markdown code fences
    if output_text.startswith("```"):
        output_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            output_text,
            flags=re.IGNORECASE,
        )

        output_text = re.sub(
            r"\s*```$",
            "",
            output_text,
        ).strip()

    try:
        return schema.model_validate_json(output_text)

    except ValidationError as exc:
        raise RuntimeError(
            "Gemini returned JSON that did not match the expected "
            f"schema.\n\nGemini output:\n{output_text}\n\n"
            f"Validation error:\n{exc}"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            "Unable to parse Gemini JSON response.\n\n"
            f"Gemini output:\n{output_text}"
        ) from exc


# ============================================================
# Build Candidate Profile
# ============================================================

def build_candidate_profile(
    resume_text: str | None = None,
    linkedin_profile_text: str | None = None,
) -> dict:
    """
    Build candidate profile from resume + LinkedIn.

    Backward compatible:
        build_candidate_profile()

    will automatically load the resume from settings.resume_path.
    """

    # --------------------------------------------------------
    # Automatically load resume if campaign.py calls:
    #
    #     build_candidate_profile()
    # --------------------------------------------------------

    if not resume_text:
        resume_path = getattr(
            settings,
            "resume_path",
            "data/resume.pdf",
        )

        try:
            resume_text = extract_resume_text(resume_path)

        except Exception as exc:
            raise RuntimeError(
                f"Could not read resume from '{resume_path}'. "
                f"Error: {exc}"
            ) from exc

    resume_text = _clean_text(resume_text)

    # --------------------------------------------------------
    # LinkedIn
    # --------------------------------------------------------

    if linkedin_profile_text is None:
        linkedin_profile_text = getattr(
            settings,
            "linkedin_profile_text",
            "",
        )

    linkedin_profile_text = _clean_text(
        linkedin_profile_text
    )

    if not resume_text:
        raise ValueError(
            "Resume text is empty. "
            "Make sure your resume PDF exists at "
            f"'{getattr(settings, 'resume_path', 'data/resume.pdf')}'."
        )

    prompt = f"""
You are an expert technical recruiter and resume analyst.

Analyze the candidate information below and create a concise,
accurate candidate profile.

IMPORTANT RULES:

1. Use ONLY information present in the provided resume and
   LinkedIn text.

2. Never invent companies, projects, education, skills,
   experience, certifications, URLs, phone numbers, or
   email addresses.

3. If information is unavailable, use an empty string,
   empty list, or 0 where appropriate.

4. Estimate experience_years only from explicit employment
   experience.

5. Keep skills specific and useful for job matching.

6. Focus on MERN, Node.js, React, JavaScript, TypeScript,
   Angular, Python, MongoDB, SQL, APIs, backend and frontend
   skills when they actually appear in the source.

7. Keep the summary concise and professional.

RESUME:
----------------
{resume_text}
----------------

LINKEDIN PROFILE:
----------------
{linkedin_profile_text}
----------------

Return only the structured candidate profile.
"""

    result = _generate_structured(
        prompt=prompt,
        schema=CandidateProfile,
    )

    return result.model_dump()


# ============================================================
# Score Job
# ============================================================

def score_job(
    candidate_profile: dict,
    job: dict,
) -> dict:
    """
    Compare candidate profile against a job.
    """

    candidate_json = _safe_json(candidate_profile)
    job_json = _safe_json(job)

    prompt = f"""
You are an experienced technical recruiter.

Evaluate how well this candidate matches this job.

CANDIDATE PROFILE:
----------------
{candidate_json}
----------------

JOB:
----------------
{job_json}
----------------

SCORING RULES:

0-39:
Very poor match. Recommend skip.

40-59:
Weak match. Recommend skip or consider.

60-74:
Reasonable match. Recommend consider.

75-89:
Strong match. Recommend apply.

90-100:
Excellent match. Recommend apply.

Consider:

- Required technical skills
- Preferred technical skills
- Years of experience
- Relevant role/title
- Frontend/backend experience
- MERN/React/Node.js experience
- JavaScript/TypeScript experience
- MongoDB/database experience
- Python/Angular experience when relevant
- Project relevance
- Overall technical fit

Do not reject the candidate simply because they do not
have every preferred skill.

A candidate can still be a strong match if they satisfy
the important requirements.

Keep the reason short and practical.
"""

    result = _generate_structured(
        prompt=prompt,
        schema=JobScore,
    )

    data = result.model_dump()

    # Normalize score
    score = float(data.get("score", 0))

    score = max(
        0.0,
        min(100.0, score),
    )

    data["score"] = score

    # Normalize recommendation
    recommendation = str(
        data.get(
            "recommendation",
            "consider",
        )
    ).lower().strip()

    if recommendation not in {
        "apply",
        "consider",
        "skip",
    }:
        if score >= 75:
            recommendation = "apply"
        elif score >= 60:
            recommendation = "consider"
        else:
            recommendation = "skip"

    data["recommendation"] = recommendation

    return data


# ============================================================
# Generate Personalized Email
# ============================================================

def generate_email(
    candidate_profile: dict,
    job: dict,
    score_result: dict | None = None,
) -> dict:
    """
    Generate personalized job application email.
    """

    candidate_json = _safe_json(candidate_profile)
    job_json = _safe_json(job)
    score_json = _safe_json(
        score_result or {}
    )

    prompt = f"""
You are a professional technical recruiter and job-application
email writer.

Write a concise, personalized job application email for this
candidate.

CANDIDATE:
----------------
{candidate_json}
----------------

JOB:
----------------
{job_json}
----------------

MATCH ANALYSIS:
----------------
{score_json}
----------------

EMAIL REQUIREMENTS:

1. Make the email sound human and professional.
2. Do not exaggerate the candidate's experience.
3. Do not invent technologies or projects.
4. Mention only skills supported by the candidate profile.
5. Clearly express interest in the specific role.
6. Mention relevant experience naturally.
7. Mention that the resume is attached.
8. Keep the email around 120-180 words.
9. Do not use emojis.
10. Do not use generic spam-like wording.
11. Do not mention the match score.
12. Do not say "I am the perfect candidate."
13. Do not include placeholders such as:
    [Company Name]
    [Hiring Manager]
    <company>
14. If a hiring manager name is not available, use:
    "Hello Hiring Team,"
15. End professionally with:

Best regards,
Pratik Raut

Create a professional subject line as well.
"""

    result = _generate_structured(
        prompt=prompt,
        schema=JobEmail,
    )

    data = result.model_dump()

    subject = _clean_text(
        data.get("subject", "")
    )

    body = str(
        data.get("body", "")
    ).strip()

    # Remove accidental markdown fences
    body = re.sub(
        r"^```(?:text)?\s*",
        "",
        body,
        flags=re.IGNORECASE,
    )

    body = re.sub(
        r"\s*```$",
        "",
        body,
    ).strip()

    # Fallback subject
    if not subject:
        company = (
            job.get("company")
            or job.get("company_name")
            or "Company"
        )

        title = (
            job.get("title")
            or job.get("job_title")
            or "Developer"
        )

        subject = (
            f"Application for {title} at {company}"
        )

    # Fallback email
    if not body:
        title = (
            job.get("title")
            or job.get("job_title")
            or "Developer"
        )

        body = (
            "Hello Hiring Team,\n\n"
            f"I am writing to express my interest in the "
            f"{title} position. I have experience in full-stack "
            "web development with technologies including React, "
            "Node.js and MongoDB.\n\n"
            "Please find my resume attached for your consideration. "
            "I would appreciate the opportunity to discuss how my "
            "experience could contribute to your team.\n\n"
            "Best regards,\n"
            "Pratik Raut"
        )

    return {
        "subject": subject,
        "body": body,
    }


# ============================================================
# Complete Application Analysis
# ============================================================

def analyze_job_application(
    resume_text: str | None = None,
    linkedin_profile_text: str | None = None,
    job: dict | None = None,
) -> dict:
    """
    Complete pipeline:

    Resume + LinkedIn
        ->
    Candidate Profile
        ->
    Job Score
        ->
    Personalized Email
    """

    if job is None:
        job = {}

    profile = build_candidate_profile(
        resume_text=resume_text,
        linkedin_profile_text=linkedin_profile_text,
    )

    score = score_job(
        candidate_profile=profile,
        job=job,
    )

    email = generate_email(
        candidate_profile=profile,
        job=job,
        score_result=score,
    )

    return {
        "candidate_profile": profile,
        "score": score,
        "email": email,
    }