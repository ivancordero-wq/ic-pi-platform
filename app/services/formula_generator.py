"""
IC-Pi Formula Generator Service
================================
Calls OpenAI GPT-4o-mini to generate measurement formulas for KPIs.
Fires after Screen 3D locks KPIs (Phase 1 deliverable).
Cost: ~$0.01-0.05 per Discovery.
"""

import os
import json
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def build_kpi_block(kpi_list):
    lines = []
    for i, kpi in enumerate(kpi_list, 1):
        lines.append(str(i) + ". KPI: " + kpi["name"])
        lines.append("   Parameter: " + kpi["parameter_name"])
        lines.append("   Description: " + kpi.get("description", "N/A"))
        lines.append("   Unit: " + kpi.get("unit", "N/A"))
        lines.append("")
    return "
".join(lines)


def build_prompt(industry, process_name, kpi_block):
    return (
        "You are an expert performance measurement consultant.

"
        "Industry: " + industry + "
"
        "Process: " + process_name + "

"
        "For each KPI below, provide:
"
        "1. A precise MEASUREMENT FORMULA (how to compute it from raw data)
"
        "2. Brief NOTES (assumptions, edge cases, or data considerations)

"
        "The formula must be specific enough that a data analyst who has never "
        "seen this KPI can compute it from source data. Use standard notation: "
        "numerator/denominator, percentages, averages, etc.

"
        "KPIs:
" + kpi_block + "

"
        "Respond in valid JSON array format. Each element must have:
"
        '- "kpi_index" (integer, matching the numbering above)
'
        '- "formula" (string, the measurement formula)
'
        '- "formula_notes" (string, brief assumptions or notes)

'
        "Return ONLY the JSON array, no other text."
    )


def generate_formulas_for_kpis(industry, process_name, kpi_list):
    """
    Given industry, process, and a list of KPI dicts,
    call GPT-4o-mini to generate measurement formulas.

    kpi_list: [{"id": uuid, "name": str, "description": str, "parameter_name": str, "unit": str}]
    Returns: [{"kpi_id": uuid, "formula": str, "formula_notes": str}]
    """
    if not OPENAI_API_KEY:
        return []

    kpi_block = build_kpi_block(kpi_list)
    prompt = build_prompt(industry, process_name, kpi_block)

    try:
        response = httpx.post(
            OPENAI_URL,
            headers={
                "Authorization": "Bearer " + OPENAI_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON (handle markdown code blocks if GPT wraps it)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        ai_results = json.loads(content)

        # Map back to kpi_ids
        output = []
        for item in ai_results:
            idx = item.get("kpi_index", 0) - 1
            if 0 <= idx < len(kpi_list):
                output.append({
                    "kpi_id": kpi_list[idx]["id"],
                    "formula": item.get("formula", ""),
                    "formula_notes": item.get("formula_notes", ""),
                })

        return output

    except Exception as e:
        print("[Formula Generator] OpenAI error: " + str(e))
        return []
