# MERN Job Application AI Agent — Ollama Edition

This version uses Ollama/local AI instead of the OpenAI API.

## 1. Install Ollama
Install Ollama from https://ollama.com/ and run:

```bash
ollama pull gpt-oss
```

You can change `OLLAMA_MODEL` in `.env` to any model installed locally.

## 2. Install Python dependencies
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure
Copy `.env.example` to `.env`. No OpenAI API key is required.

Ollama normally runs at `http://localhost:11434`.

## 4. Start
```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs

The AI uses Ollama structured JSON output for profile extraction, job scoring and email generation. Human approval remains required before sending email.
