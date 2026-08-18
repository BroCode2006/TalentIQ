# TalentIQ — Multi-Agent Resume Intelligence

## Setup (do this once)

```bash
# 1. Make sure Python 3.10+ is installed
python --version

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set your Gemini API key (or enter it in the UI)
# Windows:
set GEMINI_API_KEY=your_key_here
# Mac/Linux:
export GEMINI_API_KEY=your_key_here
```

## Run

```bash
uvicorn api:app --reload --port 8000
```

Then open: http://localhost:8000

## How to use

1. Upload one or more resumes (PDF, DOCX, or TXT)
2. Paste the job description
3. Enter your Gemini API key (get one free at aistudio.google.com)
4. Click Analyze
5. See ranked candidates with scores, matched skills, gaps, and suggestions

## Project structure

```
ps10/
  agents/
    parser.py        # Agent 1 — reads PDF/DOCX, extracts structured data
    normalizer.py    # Agent 2 — maps skills to canonical taxonomy
    matcher.py       # Agent 3 — scores candidate vs job description
  data/
    taxonomy.json    # 200+ skills with aliases and hierarchy
  frontend/
    index.html       # Full dashboard UI
  orchestrator.py    # Chains all 3 agents, handles errors
  api.py             # FastAPI backend with all endpoints
  requirements.txt
```

## API endpoints

- POST /api/v1/parse         — single resume upload + job description
- POST /api/v1/parse/batch   — multiple resumes at once
- GET  /api/v1/jobs/{id}/candidates — get results for a job
- GET  /api/v1/skills/taxonomy      — browse skill database
- GET  /api/v1/health               — health check
