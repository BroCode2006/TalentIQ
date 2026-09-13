import time
from agents.parser import parse_resume
from agents.normalizer import normalize_skills
from agents.matcher import match_candidate_to_job


def run_pipeline(
    file_path: str,
    job_description: str,
    hf_api_key: str,
    candidate_id: str = None
) -> dict:
    result = {
        "candidate_id": candidate_id or f"cand_{int(time.time())}",
        "file": file_path,
        "status": "processing",
        "stages": {},
        "final": None,
        "error": None,
        "processing_time_seconds": 0
    }
    start = time.time()

    # Stage 1 — Parse
    try:
        parsed = parse_resume(file_path, hf_api_key)
        if "error" in parsed:
            result["status"] = "partial"
            result["error"] = f"Parsing issue: {parsed['error']}"
            result["stages"]["parsing"] = {"status": "failed", "data": parsed}
        else:
            result["stages"]["parsing"] = {"status": "success", "data": parsed}
    except Exception as e:
        result["status"] = "failed"
        result["error"] = f"Parser crashed: {str(e)}"
        result["processing_time_seconds"] = round(time.time() - start, 2)
        return result

    # Stage 2 — Normalize
    try:
        raw_skills = parsed.get("skills", [])
        for proj in parsed.get("projects", []):
            raw_skills += proj.get("technologies", [])

        raw_skills = list(set(raw_skills))
        normalized = normalize_skills(raw_skills, hf_api_key)
        result["stages"]["normalization"] = {"status": "success", "data": normalized}
    except Exception as e:
        result["status"] = "partial"
        result["error"] = f"Normalization issue: {str(e)}"
        normalized = {"normalized_skills": raw_skills, "skill_mapping": {}, "skill_hierarchy": {}, "total_skills": len(raw_skills)}
        result["stages"]["normalization"] = {"status": "failed_fallback", "data": normalized}

    # Stage 3 — Match
    try:
        match_result = match_candidate_to_job(
            parsed, job_description, normalized, hf_api_key
        )
        result["stages"]["matching"] = {"status": "success", "data": match_result}
    except Exception as e:
        result["status"] = "partial"
        result["error"] = f"Matching issue: {str(e)}"
        result["stages"]["matching"] = {"status": "failed", "data": {}}
        result["processing_time_seconds"] = round(time.time() - start, 2)
        return result

    result["status"] = "success"
    result["processing_time_seconds"] = round(time.time() - start, 2)
    result["final"] = {
        "candidate_id": result["candidate_id"],
        "name": parsed.get("name", "Unknown"),
        "email": parsed.get("email", ""),
        "total_experience_years": parsed.get("total_experience_years", 0),
        "normalized_skills": normalized.get("normalized_skills", []),
        "skill_hierarchy": normalized.get("skill_hierarchy", {}),
        "overall_score": match_result.get("overall_score", 0),
        "grade": match_result.get("grade", "N/A"),
        "verdict": match_result.get("verdict", ""),
        "matched_skills": match_result.get("matched_skills", []),
        "missing_skills": match_result.get("missing_skills", []),
        "bonus_skills": match_result.get("bonus_skills", []),
        "strengths": match_result.get("strengths", []),
        "gaps": match_result.get("gaps", []),
        "upskilling_suggestions": match_result.get("upskilling_suggestions", []),
        "summary": match_result.get("summary", ""),
        "processing_time_seconds": result["processing_time_seconds"]
    }

    return result


def run_batch_pipeline(
    file_paths: list[str],
    job_description: str,
    hf_api_key: str
) -> dict:
    results = []
    for i, file_path in enumerate(file_paths):
        candidate_id = f"cand_{i+1:03d}"
        result = run_pipeline(file_path, job_description, hf_api_key, candidate_id)
        if result.get("final"):
            results.append(result["final"])

    results.sort(key=lambda x: x.get("overall_score", 0), reverse=True)

    for i, r in enumerate(results):
        r["rank"] = i + 1

    return {
        "total_processed": len(file_paths),
        "successful": len(results),
        "ranked_candidates": results
    }
