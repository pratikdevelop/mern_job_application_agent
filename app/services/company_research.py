from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings
from .job_import import clean, load_master_jobs, save_master_jobs

BLOCKED = {"naukri.com", "indeed.com", "linkedin.com", "glassdoor.com", "ambitionbox.com", "foundit.in", "monster.com", "facebook.com", "instagram.com"}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def base_domain(url: str) -> str:
    host = urlparse(clean(url)).netloc.lower().split("@")[(-1)].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def blocked(url: str) -> bool:
    host = base_domain(url)
    return any(host == d or host.endswith("." + d) for d in BLOCKED)


def result_url(href: str) -> str:
    if not href:
        return ""
    p = urlparse(href)
    uddg = parse_qs(p.query).get("uddg")
    if uddg:
        return unquote(uddg[0])
    if href.startswith("//"):
        return "https:" + href
    return href if href.startswith(("http://", "https://")) else ""


def tokens(company: str) -> set[str]:
    ignore = {"pvt", "private", "ltd", "limited", "llp", "inc", "india", "technologies", "technology", "solutions", "systems", "software", "services"}
    return {x for x in re.findall(r"[a-z0-9]+", company.lower()) if len(x) >= 3 and x not in ignore}


def find_official(client: httpx.Client, company: str) -> str:
    query = quote_plus(f'"{company}" official website careers')
    try:
        r = client.get(settings.research_search_url.format(query=query))
        r.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    wanted = tokens(company)
    candidates = []
    for a in soup.find_all("a"):
        href = result_url(a.get("href", ""))
        if not href or blocked(href):
            continue
        if urlparse(href).scheme not in ("http", "https"):
            continue
        host = base_domain(href)
        text = a.get_text(" ", strip=True).lower()
        score = sum(3 for t in wanted if t in host) + sum(1 for t in wanted if t in text)
        if score:
            candidates.append((score, href))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1].split("#")[0] if candidates else ""


def fetch(client: httpx.Client, url: str) -> tuple[str, str]:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            return "", ""
        return r.text, str(r.url)
    except Exception:
        return "", ""


def find_link(soup: BeautifulSoup, base: str, words: tuple[str, ...]) -> str:
    for a in soup.find_all("a"):
        href = clean(a.get("href"))
        text = a.get_text(" ", strip=True).lower()
        combo = f"{text} {href.lower()}"
        if any(w in combo for w in words):
            candidate = urljoin(base, href)
            if urlparse(candidate).scheme in ("http", "https") and base_domain(candidate) == base_domain(base):
                return candidate
    return ""


def emails(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found = set(EMAIL_RE.findall(soup.get_text(" ", strip=True) + " " + html))
    return sorted(x.lower() for x in found)


def choose_email(found: list[str], domain: str) -> tuple[str, str]:
    if not found:
        return "", ""
    official = [e for e in found if e.split("@", 1)[-1] == domain or e.split("@", 1)[-1].endswith("." + domain)]
    pool = official or found
    preferred = ("careers", "career", "recruit", "recruitment", "hr", "jobs", "job", "talent", "hiring")
    for e in pool:
        if e.split("@", 1)[0] in preferred:
            return e, "High" if official else "Medium"
    return pool[0], "High" if official else "Low"


def opening_titles(soup: BeautifulSoup) -> list[str]:
    keywords = ("developer", "engineer", "software", "react", "node", "python", "frontend", "backend", "full stack", "devops", "qa", "data", "ai", "genai", "intern")
    found, seen = [], set()
    for a in soup.find_all("a"):
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        low = text.lower()
        if 4 <= len(text) <= 160 and any(k in low for k in keywords) and low not in seen:
            seen.add(low)
            found.append(text)
        if len(found) >= 12:
            break
    return found


def research_row(client: httpx.Client, row: dict) -> dict:
    result = dict(row)
    result["research_status"] = "failed"
    result["research_error"] = ""
    result["researched_at"] = ""
    company = clean(row.get("company"))
    if not company:
        result["research_error"] = "Missing company name."
        return result

    website = clean(row.get("company_website")) or find_official(client, company)
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    if not website:
        result["research_error"] = "Official company website not found."
        return result

    home_html, final_home = fetch(client, website)
    if not home_html:
        result["research_error"] = "Official website could not be fetched."
        result["company_website"] = website
        return result
    website = final_home or website
    domain = base_domain(website)
    home = BeautifulSoup(home_html, "html.parser")
    careers = clean(row.get("careers_url")) or find_link(home, website, ("career", "jobs", "join us", "work with us"))
    contact = find_link(home, website, ("contact", "reach us"))

    email = clean(row.get("hr_email"))
    confidence = clean(row.get("email_confidence")) or ("Imported" if email else "")
    email_source = clean(row.get("email_source_url"))
    openings: list[str] = []

    for kind, page in (("careers", careers), ("contact", contact), ("home", website)):
        if not page:
            continue
        html, final_url = fetch(client, page)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        if not email:
            email, confidence = choose_email(emails(html), domain)
            if email:
                email_source = final_url or page
        if kind == "careers":
            openings = opening_titles(soup)

    result.update({
        "company_website": website,
        "careers_url": careers,
        "hr_email": email,
        "email_source_url": email_source,
        "email_confidence": confidence,
        "current_openings": " | ".join(dict.fromkeys(openings)),
        "research_status": "researched",
        "research_error": "",
        "researched_at": datetime.now().isoformat(timespec="seconds"),
    })
    return result


def research_master_jobs(limit: int = 10, force: bool = False) -> dict:
    rows = load_master_jobs()
    if not rows:
        return {"processed": 0, "researched": 0, "failed": 0, "total": 0}
    selected = []
    for i, row in enumerate(rows):
        if not force and clean(row.get("research_status")).lower() == "researched":
            continue
        selected.append(i)
        if len(selected) >= max(1, min(int(limit), 100)):
            break
    if not selected:
        return {"processed": 0, "researched": 0, "failed": 0, "total": len(rows), "path": settings.master_jobs_path}

    headers = {"User-Agent": settings.research_user_agent}
    with httpx.Client(timeout=float(settings.research_timeout_seconds), headers=headers, follow_redirects=True) as client:
        for i in selected:
            rows[i] = research_row(client, rows[i])
    save_master_jobs(rows)
    researched = sum(1 for i in selected if clean(rows[i].get("research_status")).lower() == "researched")
    return {"processed": len(selected), "researched": researched, "failed": len(selected) - researched, "total": len(rows), "path": settings.master_jobs_path}
