from __future__ import annotations

import json
import re
from typing import Any, List

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services.resume import extract_resume_text


# ============================================================
# GROQ CONFIGURATION
# ============================================================

GROQ_API_KEY = getattr(settings, "groq_api_key", "") or ""

GROQ_MODEL = (
    getattr(settings, "groq_model", "")
    or "openai/gpt-oss-20b"
)

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is missing. "
        "Add GROQ_API_KEY=your_key to your .env file."
    )

client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# PYDANTIC SCHEMAS
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

    contact: ContactInfo = Field(
        default_factory=ContactInfo
    )

    linkedin_url: str = ""
    summary: str = ""


class JobScore(BaseModel):
    score: float
    reason: str
    matching_skills: List[str]
    missing_skills: List[str]
    recommendation: str


class JobEmail(BaseModel):
    subject: str
    body: str


# ============================================================
# HELPERS
# ============================================================

def _clean_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


def _safe_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _schema_for(model: type[BaseModel]) -> dict:
    """
    Convert Pydantic schema to Groq strict JSON schema.

    Groq strict structured output requires:
    - all fields required
    - additionalProperties = false
    """

    schema = model.model_json_schema()

    def clean_object(obj: Any) -> Any:
        if isinstance(obj, dict):

            # Groq strict mode requires this for objects
            if obj.get("type") == "object":
                obj["additionalProperties"] = False

                if "properties" in obj:
                    obj["required"] = list(
                        obj["properties"].keys()
                    )

            # Handle nested objects
            for key, value in list(obj.items()):
                obj[key] = clean_object(value)

            return obj

        if isinstance(obj, list):
            return [
                clean_object(item)
                for item in obj
            ]

        return obj

    return clean_object(schema)


def _generate_structured(
    prompt: str,
    schema: type[BaseModel],
) -> BaseModel:
    """
    Generate a strict structured response using Groq.
    """

    json_schema = _schema_for(schema)

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional technical "
                        "recruiter and job application assistant. "
                        "Follow the requested JSON schema exactly."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],

            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "strict": True,
                    "schema": json_schema,
                },
            },

            reasoning_effort="low",
        )

    except Exception as exc:
        raise RuntimeError(
            f"Groq API request failed using model "
            f"'{GROQ_MODEL}': {exc}"
        ) from exc

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        raise RuntimeError(
            "Groq returned an empty response."
        )

    content = content.strip()

    # Safety cleanup in case markdown fences appear.
    if content.startswith("```"):
        content = re.sub(
            r"^```(?:json)?\s*",
            "",
            content,
            flags=re.IGNORECASE,
        )

        content = re.sub(
            r"\s*```$",
            "",
            content,
        ).strip()

    try:
        return schema.model_validate_json(content)

    except ValidationError as exc:
        raise RuntimeError(
            "Groq returned JSON that did not match "
            "the expected schema.\n\n"
            f"Response:\n{content}\n\n"
            f"Validation error:\n{exc}"
        ) from exc

    except Exception as exc:
        raise RuntimeError(
            "Unable to parse Groq response.\n\n"
            f"Response:\n{content}"
        ) from exc


# ============================================================
# BUILD CANDIDATE PROFILE
# ============================================================

def build_candidate_profile(
    resume_text: str | None = None,
    linkedin_profile_text: str | None = None,
) -> dict:
    """
    Build candidate profile.

    Supports both:

        build_candidate_profile()

    and:

        build_candidate_profile(
            resume_text,
            linkedin_profile_text
        )
    """

    # --------------------------------------------------------
    # Automatically load resume
    # --------------------------------------------------------

    if not resume_text:

        resume_path = getattr(
            settings,
            "resume_path",
            "data/resume.pdf",
        )

        try:
            resume_text = extract_resume_text(
                resume_path
            )

        except Exception as exc:
            raise RuntimeError(
                f"Could not read resume from "
                f"'{resume_path}'. Error: {exc}"
            ) from exc

    resume_text = _clean_text(
        resume_text
    )

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
            "Resume text is empty."
        )

    prompt = f"""
Analyze the candidate resume and LinkedIn information.

Create an accurate candidate profile.

IMPORTANT:

1. Use ONLY information present in the provided data.
2. Never invent experience.
3. Never invent companies.
4. Never invent projects.
5. Never invent skills.
6. Never invent education.
7. Never invent contact information.
8. Never invent LinkedIn URLs.
9. If information is unavailable, use empty values.
10. Estimate experience only from actual employment information.
11. Extract relevant technical skills accurately.
12. Focus on MERN, React, Node.js, JavaScript,
    TypeScript, Angular, Python, MongoDB, SQL,
    APIs, frontend and backend skills when present.
13. Keep the summary concise.

RESUME
==================================================

{resume_text}

==================================================

LINKEDIN
==================================================

{linkedin_profile_text}

==================================================

Return the candidate profile.
"""

    result = _generate_structured(
        prompt,
        CandidateProfile,
    )

    return result.model_dump()


# ============================================================
# SCORE JOB
# ============================================================

def score_job(
    candidate_profile: dict,
    job: dict,
) -> dict:
    """
    Score candidate against a job from 0 to 100.
    """

    candidate_json = _safe_json(
        candidate_profile
    )

    job_json = _safe_json(
        job
    )

    prompt = f"""
Evaluate how well the candidate matches the job.

CANDIDATE
==================================================

{candidate_json}

==================================================

JOB
==================================================

{job_json}

==================================================

SCORING:

0-39:
Very poor match. Recommendation = skip.

40-59:
Weak match. Recommendation = skip.

60-74:
Reasonable match. Recommendation = consider.

75-89:
Strong match. Recommendation = apply.

90-100:
Excellent match. Recommendation = apply.

Consider:

- Required skills
- Preferred skills
- Years of experience
- Job title
- Relevant projects
- Frontend experience
- Backend experience
- React
- Node.js
- JavaScript
- TypeScript
- MongoDB
- Angular
- Python
- APIs
- Overall technical fit

Do not require every preferred skill.

Do not reject the candidate simply because
one technology is missing.

Keep the reason concise.

The recommendation MUST be exactly one of:

apply
consider
skip
"""

    result = _generate_structured(
        prompt,
        JobScore,
    )

    data = result.model_dump()

    score = float(
        data.get("score", 0)
    )

    score = max(
        0.0,
        min(100.0, score),
    )

    data["score"] = score

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
# GENERATE JOB APPLICATION EMAIL
# ============================================================

def generate_email(
    candidate_profile: dict,
    job: dict,
    score_result: dict | None = None,
) -> dict:
    """
    Generate personalized application email.
    """

    candidate_json = _safe_json(
        candidate_profile
    )

    job_json = _safe_json(
        job
    )

    score_json = _safe_json(
        score_result or {}
    )

    prompt = f"""
Write a professional personalized job application email.

CANDIDATE
==================================================

{candidate_json}

==================================================

JOB
==================================================

{job_json}

==================================================

MATCH ANALYSIS
==================================================

{score_json}

==================================================

EMAIL RULES:

1. Sound human and professional.
2. Do not exaggerate.
3. Do not invent experience.
4. Do not invent projects.
5. Do not invent technologies.
6. Mention relevant candidate skills naturally.
7. Clearly mention the position.
8. Mention that the resume is attached.
9. Keep it approximately 120-180 words.
10. Do not mention the match score.
11. Do not use emojis.
12. Do not use spam-like language.
13. Do not say "I am the perfect candidate."
14. Do not use placeholders.
15. If no hiring manager is provided, start with:

Hello Hiring Team,

16. End exactly with:

Best regards,
Pratik Raut
"""

    result = _generate_structured(
        prompt,
        JobEmail,
    )

    data = result.model_dump()

    subject = _clean_text(
        data.get("subject", "")
    )

    body = str(
        data.get("body", "")
    ).strip()

    # --------------------------------------------------------
    # Remove accidental markdown fences
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Fallback subject
    # --------------------------------------------------------

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
            f"Application for {title} "
            f"at {company}"
        )

    # --------------------------------------------------------
    # Fallback email
    # --------------------------------------------------------

    if not body:

        title = (
            job.get("title")
            or job.get("job_title")
            or "Developer"
        )

        body = (
            "Hello Hiring Team,\n\n"
            f"I am writing to express my interest in the "
            f"{title} position. I have experience in "
            "full-stack web development with technologies "
            "including React, Node.js and MongoDB.\n\n"
            "Please find my resume attached for your "
            "consideration. I would appreciate the opportunity "
            "to discuss how my experience could contribute "
            "to your team.\n\n"
            "Best regards,\n"
            "Pratik Raut"
        )

    return {
        "subject": subject,
        "body": body,
    }


# ============================================================
# COMPLETE PIPELINE
# ============================================================

def analyze_job_application(
    resume_text: str | None = None,
    linkedin_profile_text: str | None = None,
    job: dict | None = None,
) -> dict:

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