import json
import re
from huggingface_hub import InferenceClient
from pathlib import Path

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


def extract_text_from_file(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        if not PDF_AVAILABLE:
            raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()

    elif suffix == ".docx":
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx not installed. Run: pip install python-docx")
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        return text.strip()

    elif suffix == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: PDF, DOCX, TXT")


def parse_resume(file_path: str, hf_api_key: str) -> dict:
    client = InferenceClient(
        model="meta-llama/Llama-3.3-70B-Instruct",
        token=hf_api_key
    )

    raw_text = extract_text_from_file(file_path)

    if not raw_text or len(raw_text) < 50:
        return {"error": "Could not extract text from resume", "raw_text": raw_text}

    prompt = f"""You are a resume parser. Extract structured information from the resume text below.

Return ONLY a valid JSON object with exactly this structure — no explanation, no markdown, no code blocks:

{{
  "name": "full name or empty string",
  "email": "email or empty string",
  "phone": "phone number or empty string",
  "location": "city, country or empty string",
  "summary": "professional summary in 1-2 sentences or empty string",
  "total_experience_years": 0,
  "skills": ["skill1", "skill2"],
  "experience": [
    {{
      "company": "company name",
      "role": "job title",
      "duration": "e.g. 2020-2022",
      "years": 2.0,
      "responsibilities": ["key responsibility 1", "key responsibility 2"]
    }}
  ],
  "education": [
    {{
      "institution": "university name",
      "degree": "degree type e.g. B.Tech",
      "field": "field of study",
      "year": "graduation year"
    }}
  ],
  "certifications": ["certification 1", "certification 2"],
  "projects": [
    {{
      "name": "project name",
      "description": "brief description",
      "technologies": ["tech1", "tech2"]
    }}
  ]
}}

Resume text:
{raw_text[:4000]}"""

    response = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
    )
    response_text = response.choices[0].message.content.strip()

    response_text = re.sub(r"```json\s*", "", response_text)
    response_text = re.sub(r"```\s*", "", response_text)
    response_text = response_text.strip()

    try:
        parsed = json.loads(response_text)
        parsed["_raw_text_length"] = len(raw_text)
        parsed["_source_file"] = Path(file_path).name
        return parsed
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                parsed["_source_file"] = Path(file_path).name
                return parsed
            except:
                pass
        return {
            "error": "Failed to parse LLM response as JSON",
            "raw_response": response_text[:500],
            "_source_file": Path(file_path).name
        }
