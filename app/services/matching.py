from __future__ import annotations

import re
from typing import Any


# ------------------------------------------------------------
# Skill aliases used by the deterministic matcher.
# The matcher intentionally uses conservative keyword matching.
# ------------------------------------------------------------

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "React": ("react", "react.js", "reactjs"),
    "Next.js": ("next.js", "nextjs"),
    "Node.js": ("node.js", "nodejs", "node"),
    "Express.js": ("express.js", "express"),
    "MongoDB": ("mongodb", "mongo db"),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "SQL": (" sql ", "sql/", "sql,", "sql."),
    "TypeScript": ("typescript",),
    "JavaScript": ("javascript",),
    "Angular": ("angular",),
    "Python": ("python",),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "REST APIs": ("rest api", "restful api", "rest apis"),
    "GraphQL": ("graphql",),
    "Redis": ("redis",),
    "Kafka": ("kafka", "apache kafka"),
    "RabbitMQ": ("rabbitmq",),
    "WebSockets": ("websocket", "websockets", "socket.io", "socket io"),
    "Docker": ("docker",),
    "AWS": ("aws", "amazon web services"),
    "CI/CD": ("ci/cd", "cicd", "continuous integration"),
    "Microservices": ("microservices", "microservice"),
    "JWT": ("jwt",),
    "RBAC": ("rbac", "role based access"),
    "LangChain": ("langchain",),
    "LangGraph": ("langgraph",),
    "RAG": ("rag", "retrieval augmented generation"),
    "LLMs": ("llm", "llms", "large language model"),
    "AI Agents": ("ai agent", "ai agents", "agentic"),
    "Generative AI": ("generative ai", "genai", "gen ai"),
}


CORE_STACK = {
    "React",
    "Node.js",
    "Express.js",
    "MongoDB",
    "TypeScript",
    "JavaScript",
    "Angular",
    "Python",
}

FRONTEND_SKILLS = {
    "React",
    "Next.js",
    "Angular",
    "TypeScript",
    "JavaScript",
}

BACKEND_SKILLS = {
    "Node.js",
    "Express.js",
    "Python",
    "FastAPI",
    "Django",
    "REST APIs",
    "GraphQL",
    "Microservices",
}

AI_SKILLS = {
    "LangChain",
    "LangGraph",
    "RAG",
    "LLMs",
    "AI Agents",
    "Generative AI",
}

CLOUD_SKILLS = {
    "AWS",
    "Docker",
    "CI/CD",
    "Kafka",
    "RabbitMQ",
    "Redis",
}


def _text(*values: Any) -> str:
    return " ".join(
        str(value or "")
        for value in values
    ).strip()


def _normalized(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+#./-]+", " ", text)
    return f" {text} "


def _contains(text: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalized(text)

    for alias in aliases:
        alias_normalized = _normalized(alias)

        if alias_normalized.strip() in normalized:
            return True

    return False


def extract_skills(text: str) -> set[str]:
    found: set[str] = set()

    for skill, aliases in SKILL_ALIASES.items():
        if _contains(text, aliases):
            found.add(skill)

    return found


def _skills_from_profile(profile: dict) -> set[str]:
    values: list[str] = []

    for field in (
        "primary_skills",
        "secondary_skills",
        "projects",
    ):
        value = profile.get(field, [])

        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))

    values.append(str(profile.get("summary", "")))
    values.append(str(profile.get("role", "")))

    return extract_skills(" ".join(values))


def _extract_required_experience(text: str) -> float | None:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        r"minimum\s+of\s+(\d+(?:\.\d+)?)",
        r"at\s+least\s+(\d+(?:\.\d+)?)",
    ]

    values: list[float] = []

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            try:
                values.append(float(match.group(1)))
            except ValueError:
                pass

    if not values:
        return None

    # Take the smallest explicit requirement. This avoids treating
    # "5+ years preferred" as the hard minimum when "3+ years required"
    # also appears in the description.
    return min(values)


def _title_score(candidate_role: str, job_title: str) -> float:
    role = _normalized(candidate_role)
    title = _normalized(job_title)

    if not title.strip():
        return 0.0

    exact_keywords = {
        "full stack": 1.0,
        "mern": 1.0,
        "react": 0.9,
        "node": 0.9,
        "software engineer": 0.8,
        "frontend": 0.75,
        "backend": 0.75,
        "developer": 0.65,
        "ai": 0.7,
        "genai": 0.75,
    }

    total = 0.0
    weight = 0.0

    for keyword, value in exact_keywords.items():
        if keyword in title:
            weight += value
            if keyword in role:
                total += value

    if weight == 0:
        # A generic developer title is still relevant to a
        # Full Stack Developer profile.
        return 0.6

    return min(1.0, total / weight)


def calculate_match(
    candidate_profile: dict,
    job: dict,
) -> dict:
    """
    Deterministic job matching.

    The LLM is not responsible for the final numeric score.
    It may later be used only for explanation/email generation.
    """

    candidate_skills = _skills_from_profile(
        candidate_profile
    )

    job_text = _text(
        job.get("title"),
        job.get("description"),
        job.get("experience"),
        job.get("work_mode"),
    )

    job_skills = extract_skills(job_text)

    matching = sorted(candidate_skills & job_skills)
    missing = sorted(job_skills - candidate_skills)

    # 1. Core stack — 25 points
    core_job = job_skills & CORE_STACK

    if core_job:
        core_matches = len(core_job & candidate_skills)
        core_score = 25.0 * (
            core_matches / len(core_job)
        )
    else:
        core_score = 17.5

    # 2. Overall required/explicit skills — 25 points
    if job_skills:
        skill_score = 25.0 * (
            len(matching) / len(job_skills)
        )
    else:
        skill_score = 17.5

    # 3. Experience — 15 points
    candidate_experience = float(
        candidate_profile.get(
            "experience_years",
            0.0,
        )
        or 0.0
    )

    required_experience = _extract_required_experience(
        job_text
    )

    if required_experience is None:
        experience_score = 12.0
    elif candidate_experience >= required_experience:
        experience_score = 15.0
    else:
        gap = required_experience - candidate_experience

        # Small gaps should not be treated harshly.
        if gap <= 0.25:
            experience_score = 14.5
        elif gap <= 0.5:
            experience_score = 13.5
        elif gap <= 1.0:
            experience_score = 11.0
        elif gap <= 2.0:
            experience_score = 8.0
        else:
            experience_score = 4.0

    # 4. Role/title relevance — 10 points
    title_relevance = _title_score(
        candidate_profile.get(
            "role",
            "Full Stack Developer",
        ),
        job.get("title", ""),
    )
    title_score = 10.0 * title_relevance

    # 5. Frontend/backend balance — 10 points
    frontend_job = job_skills & FRONTEND_SKILLS
    backend_job = job_skills & BACKEND_SKILLS

    frontend_ratio = (
        len(frontend_job & candidate_skills)
        / len(frontend_job)
        if frontend_job
        else 0.5
    )

    backend_ratio = (
        len(backend_job & candidate_skills)
        / len(backend_job)
        if backend_job
        else 0.5
    )

    frontend_backend_score = 10.0 * (
        0.5 * frontend_ratio
        + 0.5 * backend_ratio
    )

    # 6. AI/GenAI relevance — 5 points
    ai_job = job_skills & AI_SKILLS
    if ai_job:
        ai_ratio = len(
            ai_job & candidate_skills
        ) / len(ai_job)
        ai_score = 5.0 * ai_ratio
    else:
        ai_score = 2.5

    # 7. Cloud/devops — 5 points
    cloud_job = job_skills & CLOUD_SKILLS
    if cloud_job:
        cloud_ratio = len(
            cloud_job & candidate_skills
        ) / len(cloud_job)
        cloud_score = 5.0 * cloud_ratio
    else:
        cloud_score = 2.5

    # 8. Work mode/location — 5 points
    # We avoid penalizing a candidate when the CSV does not
    # contain a clear constraint.
    work_mode = str(
        job.get("work_mode", "")
    ).lower()

    if not work_mode:
        work_mode_score = 5.0
    elif any(
        token in work_mode
        for token in (
            "remote",
            "hybrid",
            "onsite",
            "on-site",
        )
    ):
        work_mode_score = 5.0
    else:
        work_mode_score = 3.0

    raw_score = (
        core_score
        + skill_score
        + experience_score
        + title_score
        + frontend_backend_score
        + ai_score
        + cloud_score
        + work_mode_score
    )

    score = round(
        max(0.0, min(100.0, raw_score)),
        1,
    )

    if score >= 80:
        recommendation = "apply"
    elif score >= 65:
        recommendation = "consider"
    else:
        recommendation = "skip"

    reasons: list[str] = []

    if matching:
        reasons.append(
            f"strong overlap in {', '.join(matching[:6])}"
        )

    if required_experience is not None:
        if candidate_experience >= required_experience:
            reasons.append(
                f"{candidate_experience:g} years meets the "
                f"{required_experience:g}+ year requirement"
            )
        elif required_experience - candidate_experience <= 0.25:
            reasons.append(
                f"{candidate_experience:g} years is within "
                f"0.25 years of the stated experience requirement"
            )

    if missing:
        reasons.append(
            f"missing or unconfirmed: {', '.join(missing[:5])}"
        )

    if not reasons:
        reasons.append(
            "limited structured job requirements were available"
        )

    reason = "; ".join(reasons)

    return {
        "score": score,
        "reason": reason,
        "matching_skills": matching,
        "missing_skills": missing,
        "recommendation": recommendation,
        "required_experience": required_experience,
        "candidate_experience": candidate_experience,
    }
