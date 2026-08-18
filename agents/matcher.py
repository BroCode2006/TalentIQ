import json
import re
from huggingface_hub import InferenceClient


def match_candidate_to_job(
    candidate_profile: dict,
    job_description: str,
    normalized_skills: dict,
    hf_api_key: str
) -> dict:
    client = InferenceClient(
        model="meta-llama/Llama-3.3-70B-Instruct",
        token=hf_api_key
    )

    name = candidate_profile.get("name", "Candidate")
    skills = normalized_skills.get("normalized_skills", [])
    experience = candidate_profile.get("experience", [])
    total_years = candidate_profile.get("total_experience_years", 0)
    education = candidate_profile.get("education", [])

    experience_summary = ""
    for exp in experience[:3]:
        experience_summary += f"- {exp.get('role', '')} at {exp.get('company', '')} ({exp.get('duration', '')})\n"

    education_summary = ""
    for edu in education[:2]:
        education_summary += f"- {edu.get('degree', '')} in {edu.get('field', '')} from {edu.get('institution', '')}\n"

    prompt = f"""You are an expert technical recruiter performing candidate-job matching.

CANDIDATE PROFILE:
Name: {name}
Total Experience: {total_years} years
Skills: {', '.join(skills)}
Experience:
{experience_summary}
Education:
{education_summary}

JOB DESCRIPTION:
{job_description[:2000]}

Perform a thorough semantic match. Return ONLY a valid JSON object with exactly this structure:

{{
  "overall_score": 78,
  "grade": "B+",
  "verdict": "Strong Match / Good Match / Partial Match / Weak Match / Not a Match",
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "bonus_skills": ["extra skill candidate has beyond requirements"],
  "experience_score": 80,
  "skills_score": 75,
  "education_score": 70,
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "gaps": ["gap 1", "gap 2"],
  "upskilling_suggestions": ["Learn X to fill gap Y", "Get certified in Z"],
  "summary": "2-3 sentence plain English explanation of this candidate's fit for the role"
}}

Scoring rules:
- overall_score is 0-100
- grade: 90-100=A, 80-89=B+, 70-79=B, 60-69=C+, 50-59=C, below 50=D
- Be semantic — ReactJS matches React requirement, ML matches Machine Learning
- Consider experience depth, not just skill presence
- Return only JSON, no explanation:"""

    response = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    response_text = response.choices[0].message.content.strip()
    response_text = re.sub(r"```json\s*", "", response_text)
    response_text = re.sub(r"```\s*", "", response_text)
    response_text = response_text.strip()

    try:
        result = json.loads(response_text)
        result["candidate_name"] = name
        result["total_experience_years"] = total_years
        return result
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                result["candidate_name"] = name
                return result
            except:
                pass
        return {
            "error": "Failed to parse match result",
            "candidate_name": name,
            "overall_score": 0,
            "grade": "N/A",
            "verdict": "Error",
            "summary": "Could not complete matching due to a parsing error."
        }
