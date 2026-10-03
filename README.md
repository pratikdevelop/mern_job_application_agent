# MERN Job Application AI Agent — Groq Edition

An AI-powered job application agent for MERN / React / Node.js roles.

The **current version uses Groq Cloud** for AI. It no longer uses Ollama.

## Features

- Extracts and analyzes your resume
- Builds a structured candidate profile
- Reads job/company CSV files
- Scores jobs against your profile
- Identifies matching and missing skills
- Generates personalized application emails
- Attaches your resume
- Prevents duplicate applications
- Maintains `data/send_log.csv`
- Enforces a daily sending limit
- Retries failed sends
- Requires human approval before sending

## 1. Requirements

- Windows 10/11
- Python 3.12+
- Gmail account
- Groq API key

The current AI implementation does **not** require Ollama.

## 2. Setup

Open PowerShell in the project directory:

```powershell
cd C:\Users\prati\Documents\python-app\mern_job_application_agent
```

Create the virtual environment:

```powershell
python -m venv venv
```

Activate it:

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If needed, install Groq explicitly:

```powershell
pip install groq
```

## 3. Configure `.env`

Create `.env` in the project root. Example:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

RESUME_PATH=data/resume.pdf

DAILY_LIMIT=15
MIN_SCORE=70

MIN_DELAY_SECONDS=45
MAX_DELAY_SECONDS=90

SEND_LOG_PATH=data/send_log.csv
```

Never commit `.env` or share your API key.

## 4. Verify Groq

Check configuration:

```powershell
python -c "from app.config import settings; print('Key loaded:', bool(settings.groq_api_key)); print('Model:', settings.groq_model)"
```

Expected:

```text
Key loaded: True
Model: openai/gpt-oss-20b
```

Test an actual request:

```powershell
python -c "from app.config import settings; from groq import Groq; c=Groq(api_key=settings.groq_api_key); r=c.chat.completions.create(model=settings.groq_model,messages=[{'role':'user','content':'Reply with exactly TEST'}]); print(r.choices[0].message.content)"
```

Expected:

```text
TEST
```

## 5. Resume and CSV files

Put your resume here unless `RESUME_PATH` is changed:

```text
data/resume.pdf
```

The campaign reads the CSV files configured in `app/config.py`.

Supported job fields include:

- Company Name
- HR / Recruitment Email
- Verified HR / Recruitment Email
- Current Opening
- MERN / Node / React Opening
- Location
- Experience
- Work Mode
- Priority
- Careers / Opening URL

Duplicate `company + email` targets are removed before processing.

# How to run

## 6. Start the FastAPI application

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

This starts the API/Swagger interface.

## 7. Run the campaign in preview mode

**Always test preview mode first. It sends no emails.**

```powershell
python run_campaign.py --limit 3
```

The campaign will:

1. Load the job/company CSVs
2. Build your candidate profile with Groq
3. Score jobs
4. Generate personalized emails
5. Display the email preview
6. Send nothing

## 8. Use a minimum score

For example, only process jobs scoring 80+:

```powershell
python run_campaign.py --limit 5 --min-score 80
```

## 9. Send one real application

After reviewing preview output:

```powershell
python run_campaign.py --send --limit 1
```

The application shows the generated email and asks:

```text
Send this email? [y/N]:
```

Enter `y` to approve that email.

After a successful send, it is recorded in:

```text
data/send_log.csv
```

## 10. Send multiple applications

For example:

```powershell
python run_campaign.py --send --limit 5
```

The configured maximum is 15 per day:

```env
DAILY_LIMIT=15
```

The effective limit is the smaller of `--limit` and `DAILY_LIMIT`.

The campaign also waits between successful emails according to:

```env
MIN_DELAY_SECONDS=45
MAX_DELAY_SECONDS=90
```

# Gmail OAuth

The application uses Gmail OAuth for sending. Keep these files private:

```text
credentials.json
token.json
```

## Google error: `403 access_denied` / app has not completed verification

If Google displays:

```text
Access blocked: app has not completed the Google verification process
The app is currently being tested, and can only be accessed by developer-approved testers.
Error 403: access_denied
```

the OAuth app is in Testing mode. Add the Gmail account you are using as a **Test user** in the Google Cloud OAuth consent-screen configuration, then retry authorization.

If an old token was created during a failed authorization, remove it locally:

```powershell
Remove-Item token.json -ErrorAction SilentlyContinue
```

Then retry:

```powershell
python run_campaign.py --send --limit 1
```

Do not share `credentials.json`, `token.json`, or your Groq API key.

# Duplicate protection

The campaign uses:

```text
company + email
```

as the application key. Successfully sent applications are stored in `data/send_log.csv` and skipped on later runs.

# Recommended workflow

```text
Activate venv
    ↓
Verify Groq
    ↓
Preview 3 jobs
    ↓
Review generated emails
    ↓
Send 1 test application
    ↓
Check Gmail delivery
    ↓
Check data/send_log.csv
    ↓
Run larger campaign
```

Quick start:

```powershell
cd C:\Users\prati\Documents\python-app\mern_job_application_agent
.\venv\Scripts\Activate.ps1
python -c "from app.config import settings; print('Key loaded:', bool(settings.groq_api_key)); print('Model:', settings.groq_model)"
python run_campaign.py --limit 3
```

Then, after checking the previews:

```powershell
python run_campaign.py --send --limit 1
```

# Current AI architecture

```text
Resume PDF
    ↓
Resume Text Extraction
    ↓
Groq — openai/gpt-oss-20b
    ├── Candidate Profile
    ├── Job Match Score
    └── Personalized Email
            ↓
      Human Approval
            ↓
       Gmail OAuth
            ↓
      Email + Resume
            ↓
      send_log.csv
```

The Groq integration uses structured JSON responses validated through Pydantic models.

# Important: Ollama instructions are obsolete

Do **not** use the old instructions:

```bash
ollama pull gpt-oss
```

or:

```env
OLLAMA_MODEL=...
OLLAMA_HOST=...
```

The current AI configuration is:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
```

# Project structure

```text
mern_job_application_agent/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   └── services/
│       ├── ai.py
│       ├── campaign.py
│       ├── gmail.py
│       └── resume.py
├── data/
│   ├── resume.pdf
│   ├── send_log.csv
│   └── *.csv
├── .env
├── .env.example
├── requirements.txt
├── run_campaign.py
└── README.md
```
