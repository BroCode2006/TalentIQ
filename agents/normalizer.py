import json
import re
from pathlib import Path
from huggingface_hub import InferenceClient


def load_taxonomy(taxonomy_path: str = None) -> dict:
    if taxonomy_path is None:
        taxonomy_path = Path(__file__).parent.parent / "data" / "taxonomy.json"
    with open(taxonomy_path, "r") as f:
        return json.load(f)


def normalize_skill_local(skill: str, taxonomy: dict) -> str | None:
    skill_lower = skill.lower().strip()
    for canonical, aliases in taxonomy["canonical_skills"].items():
        if skill_lower == canonical.lower():
            return canonical
        if skill_lower in [a.lower() for a in aliases]:
            return canonical
    return None


def normalize_skills(
    raw_skills: list[str],
    hf_api_key: str,
    taxonomy_path: str = None
) -> dict:
    taxonomy = load_taxonomy(taxonomy_path)
    normalized = []
    unknown = []
    mapping = {}

    for skill in raw_skills:
        if not skill or not skill.strip():
            continue
        canonical = normalize_skill_local(skill, taxonomy)
        if canonical:
            normalized.append(canonical)
            mapping[skill] = canonical
        else:
            unknown.append(skill)

    if unknown:
        client = InferenceClient(
            model="meta-llama/Llama-3.3-70B-Instruct",
            token=hf_api_key
        )

        known_canonicals = list(taxonomy["canonical_skills"].keys())

        prompt = f"""You are a skill normalization expert. Map each skill below to its canonical name.

Known canonical skills:
{json.dumps(known_canonicals[:100], indent=2)}

Skills to map:
{json.dumps(unknown)}

Return ONLY a valid JSON object mapping each input skill to either:
- A canonical skill name from the list above (if it matches)
- The cleaned/standardized version of the skill (if it's new but valid)
- null (if it's not a real technical or professional skill)

Example: {{"ReactJS": "React", "K8s": "Kubernetes", "cooking": null}}

Return only the JSON, no explanation:"""

        response = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        response_text = response.choices[0].message.content.strip()
        response_text = re.sub(r"```json\s*", "", response_text)
        response_text = re.sub(r"```\s*", "", response_text)

        try:
            llm_mapping = json.loads(response_text)
            for original, mapped in llm_mapping.items():
                if mapped:
                    normalized.append(mapped)
                    mapping[original] = mapped
                else:
                    mapping[original] = None
        except json.JSONDecodeError:
            for skill in unknown:
                normalized.append(skill)
                mapping[skill] = skill

    normalized = list(dict.fromkeys(normalized))

    skill_hierarchy = {}
    for skill in normalized:
        for category, subcategories in taxonomy["hierarchy"].items():
            for subcategory, skills_list in subcategories.items():
                if skill in skills_list:
                    if category not in skill_hierarchy:
                        skill_hierarchy[category] = {}
                    if subcategory not in skill_hierarchy[category]:
                        skill_hierarchy[category][subcategory] = []
                    skill_hierarchy[category][subcategory].append(skill)

    return {
        "normalized_skills": normalized,
        "skill_mapping": mapping,
        "skill_hierarchy": skill_hierarchy,
        "total_skills": len(normalized)
    }
