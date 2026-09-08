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
    return "\n".join(lines)


def build_prompt(industry, process_name, kpi_block, country=""):
    parts = []
    parts.append("You are an expert performance measurement consultant.")
    parts.append("")
    parts.append("Industry: " + industry)
    parts.append("Process: " + process_name)
    if country:
        parts.append("Country: " + country)
        parts.append("")
        parts.append("CRITICAL CONTEXT REQUIREMENT:")
        parts.append("This organization operates in the " + industry + " industry in " + country + ".")
        parts.append("Every formula and note MUST reflect that reality:")
        parts.append("- Express monetary values in the local currency of " + country + ".")
        parts.append("- Name data sources that plausibly exist in a " + industry + " organization in " + country + ", such as local systems, registries or manual records. Do not assume US vendor products.")
        parts.append("- Reference the regulatory or reporting framework that actually applies in " + country + " for this industry instead of generic SLAs.")
        parts.append("- Use terminology a local practitioner in " + country + " would recognize.")
        parts.append("- If a measurement is not realistically collectable there, say so in the notes and propose the locally viable proxy.")
    parts.append("")
    parts.append("For each KPI below, provide:")
    parts.append("1. A precise MEASUREMENT FORMULA (how to compute it from raw data)")
    parts.append("2. Brief NOTES (assumptions, edge cases, or data considerations)")
    parts.append("")
    parts.append("The formula must be specific enough that a data analyst who has never")
    parts.append("seen this KPI can compute it from source data. Use standard notation:")
    parts.append("numerator/denominator, percentages, averages, etc.")
    parts.append("")
    parts.append("KPIs:")
    parts.append(kpi_block)
    parts.append("")
    parts.append("Respond in valid JSON array format. Each element must have:")
    parts.append('- "kpi_index" (integer, matching the numbering above)')
    parts.append('- "formula" (string, the measurement formula)')
    parts.append('- "formula_notes" (string, brief assumptions or notes)')
    parts.append("")
    parts.append("Return ONLY the JSON array, no other text.")
    return "\n".join(parts)


def generate_formulas_for_kpis(industry, process_name, kpi_list, country=""):
    if not OPENAI_API_KEY:
        return []

    kpi_block = build_kpi_block(kpi_list)
    prompt = build_prompt(industry, process_name, kpi_block, country)

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

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        ai_results = json.loads(content)

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
