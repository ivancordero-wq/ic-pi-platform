import os
from openai import OpenAI
"""
IC-Pi AI-Hybrid Service
========================
Process disambiguation and parameter generation.
Currently uses curated knowledge base. Architecture ready for LLM API swap.
"""

# Canonical process names by industry (semantic matching target)
PROCESS_CATALOG = {
    "Insurance": [
        "Claims Processing & Adjudication",
        "Fraud Detection & Investigation",
        "Underwriting Risk Assessment",
        "Policy Renewal & Retention",
        "Customer Onboarding & KYC",
        "Reinsurance Treaty Management",
        "Premium Collection & Reconciliation",
        "Loss Ratio Optimization",
        "Agent Commission Management",
        "Regulatory Compliance Reporting",
    ],
    "Banking & Financial Services": [
        "Loan Origination & Approval",
        "Anti-Money Laundering (AML) Monitoring",
        "Credit Risk Assessment",
        "Payment Processing & Settlement",
        "Customer Onboarding & KYC",
        "Fraud Detection & Prevention",
        "Treasury & Liquidity Management",
        "Mortgage Servicing Operations",
        "Branch Operations Efficiency",
        "Regulatory Capital Reporting",
    ],
    "Healthcare": [
        "Patient Intake & Registration",
        "Revenue Cycle Management",
        "Clinical Documentation & Coding",
        "Supply Chain & Inventory Management",
        "Discharge Planning & Care Transitions",
        "Claims Denial Management",
        "Operating Room Scheduling & Utilization",
        "Medication Administration & Safety",
        "Patient Flow & Bed Management",
        "Quality Metrics & Accreditation Compliance",
    ],
    "Manufacturing": [
        "Production Planning & Scheduling",
        "Quality Control & Defect Reduction",
        "Supply Chain & Procurement",
        "Preventive Maintenance & Asset Reliability",
        "Warehouse & Inventory Management",
        "Order Fulfillment & Logistics",
        "Energy Consumption Optimization",
        "Safety Incident Management",
        "New Product Introduction (NPI)",
        "Supplier Quality Management",
    ],
    "Oil & Gas": [
        "Drilling Operations Optimization",
        "Production Allocation & Reporting",
        "HSE Incident Management",
        "Turnaround & Maintenance Planning",
        "Reservoir Performance Monitoring",
        "Supply Chain & Materials Management",
        "Well Integrity Management",
        "Pipeline Operations & Monitoring",
        "Regulatory Compliance & Permitting",
        "Workforce Scheduling & Competency",
    ],
}

# Parameters associated with canonical processes
PARAMETER_CATALOG = {
    "Claims Processing & Adjudication": [
        {"name": "Average Claim Cycle Time", "source": "standard", "description": "End-to-end days from FNOL to payment"},
        {"name": "Straight-Through Processing Rate", "source": "standard", "description": "Percentage of claims auto-adjudicated without human touch"},
        {"name": "Claim Leakage Rate", "source": "standard", "description": "Overpayments due to adjudication errors"},
        {"name": "Adjuster Workload Balance", "source": "standard", "description": "Claims per adjuster vs optimal threshold"},
        {"name": "Document Completeness at FNOL", "source": "standard", "description": "Percentage of claims with all required docs at first notice"},
        {"name": "Reopened Claims Rate", "source": "standard", "description": "Claims reopened after initial closure"},
        {"name": "Reserve Accuracy", "source": "regulation", "description": "Deviation between initial reserve and final paid amount"},
        {"name": "Litigation Rate", "source": "standard", "description": "Percentage of claims escalating to legal"},
        {"name": "Customer Satisfaction (Claims NPS)", "source": "standard", "description": "Post-claim survey score"},
        {"name": "Subrogation Recovery Rate", "source": "ai", "description": "Percentage of recoverable amounts actually collected"},
        {"name": "Fraud Flag Accuracy", "source": "ai", "description": "Precision of automated fraud indicators during claims"},
        {"name": "First Contact Resolution Rate", "source": "ai", "description": "Claims resolved in single interaction with claimant"},
    ],
    "Fraud Detection & Investigation": [
        {"name": "Detection Rate (True Positive)", "source": "standard", "description": "Percentage of actual fraud caught by the system"},
        {"name": "False Positive Rate", "source": "standard", "description": "Legitimate transactions flagged incorrectly"},
        {"name": "Mean Time to Investigate", "source": "standard", "description": "Average hours from alert to disposition"},
        {"name": "Recovery Rate on Confirmed Fraud", "source": "standard", "description": "Percentage of fraudulent amount recovered"},
        {"name": "Alert-to-Case Conversion Rate", "source": "standard", "description": "Percentage of alerts escalated to full investigation"},
        {"name": "Investigator Caseload", "source": "standard", "description": "Open cases per investigator vs benchmark"},
        {"name": "Model Drift Monitoring", "source": "ai", "description": "Decay rate of detection model accuracy over time"},
        {"name": "Network Analysis Coverage", "source": "ai", "description": "Percentage of claims analyzed for ring/network patterns"},
        {"name": "Regulatory Reporting Timeliness", "source": "regulation", "description": "SARs filed within mandated deadlines"},
        {"name": "Cost per Investigation", "source": "standard", "description": "Total investigation cost relative to recovered amount"},
        {"name": "Repeat Offender Identification", "source": "ai", "description": "Known-fraud entity matching across new claims"},
        {"name": "Data Quality Score (Input Feeds)", "source": "ai", "description": "Completeness and accuracy of data feeding detection models"},
    ],
    "Underwriting Risk Assessment": [
        {"name": "Quote-to-Bind Ratio", "source": "standard", "description": "Percentage of quotes that convert to bound policies"},
        {"name": "Underwriting Cycle Time", "source": "standard", "description": "Days from submission to decision"},
        {"name": "Loss Ratio by Underwriter", "source": "standard", "description": "Claims paid vs premiums earned per underwriter"},
        {"name": "Risk Selection Accuracy", "source": "standard", "description": "Actual vs predicted loss frequency"},
        {"name": "Pricing Adequacy", "source": "standard", "description": "Premium charged vs actuarial indicated rate"},
        {"name": "Referral Rate to Senior UW", "source": "standard", "description": "Percentage of submissions needing escalation"},
        {"name": "Data Enrichment Utilization", "source": "ai", "description": "External data sources consumed per decision"},
        {"name": "Appetite Compliance", "source": "regulation", "description": "Submissions accepted within defined risk appetite"},
        {"name": "Renewal Retention Rate", "source": "standard", "description": "Policies renewed vs lapsed at expiry"},
        {"name": "Exception-to-Guidelines Rate", "source": "standard", "description": "Decisions made outside standard guidelines"},
    ],
    "Loan Origination & Approval": [
        {"name": "Application-to-Approval Cycle Time", "source": "standard", "description": "Days from application to final decision"},
        {"name": "Approval Rate", "source": "standard", "description": "Percentage of applications approved"},
        {"name": "Document Collection Completeness", "source": "standard", "description": "First-time completeness of required documentation"},
        {"name": "Credit Decision Accuracy", "source": "standard", "description": "Default rate vs predicted risk at origination"},
        {"name": "Cost per Originated Loan", "source": "standard", "description": "Total operational cost per funded loan"},
        {"name": "Abandonment Rate", "source": "standard", "description": "Applications started but not completed"},
        {"name": "Automated Decision Rate", "source": "ai", "description": "Percentage decided without human underwriter"},
        {"name": "Compliance Check Pass Rate", "source": "regulation", "description": "Applications passing all regulatory checks first time"},
        {"name": "Cross-Sell Attachment Rate", "source": "ai", "description": "Additional products sold during origination"},
        {"name": "Channel Efficiency", "source": "standard", "description": "Cost and speed comparison across origination channels"},
    ],
    "Production Planning & Scheduling": [
        {"name": "Schedule Adherence", "source": "standard", "description": "Percentage of production runs completed on schedule"},
        {"name": "Overall Equipment Effectiveness (OEE)", "source": "standard", "description": "Availability x Performance x Quality"},
        {"name": "Changeover Time", "source": "standard", "description": "Minutes lost between product/batch switches"},
        {"name": "Capacity Utilization Rate", "source": "standard", "description": "Actual output vs maximum possible output"},
        {"name": "Work-in-Progress (WIP) Inventory Levels", "source": "standard", "description": "Units in production pipeline vs target"},
        {"name": "Order Lead Time Accuracy", "source": "standard", "description": "Promised vs actual delivery dates"},
        {"name": "Demand Forecast Accuracy", "source": "ai", "description": "Predicted vs actual demand variance"},
        {"name": "Scrap & Rework Rate", "source": "standard", "description": "Percentage of output requiring rework or disposal"},
        {"name": "Labor Productivity", "source": "standard", "description": "Units produced per labor hour"},
        {"name": "Material Availability at Schedule", "source": "standard", "description": "Percentage of runs with all materials ready at start"},
    ],
}


def disambiguate_process(industry: str, user_input: str) -> dict:
    """
    Given an industry and user-typed process name, return ranked canonical matches.
    Uses OpenAI GPT-4o-mini for AI-powered disambiguation.
    Falls back to keyword matching if no API key available.
    """
    user_lower = user_input.lower().strip()

    # Try AI-powered disambiguation first
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            client = OpenAI(api_key=openai_key)
            prompt = (
                f"You are an expert in business process taxonomy across all industries. "
                f"A consultant entered the following process description for a client in the '{industry}' industry: "
                f"'{user_input}'. "
                f"Suggest 5 canonical process names that best match what this client likely means. "
                f"These should be standard, recognizable process names used in {industry} organizations. "
                f"Rank them from best fit to least fit. "
                f"Format: return ONLY the process names, one per line, numbered 1-5. No explanations."
            )
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            ai_text = response.choices[0].message.content.strip()

            # Parse numbered lines into list
            matches = []
            for line in ai_text.split("\n"):
                line = line.strip()
                if line:
                    # Remove numbering (1. or 1) or - prefix)
                    cleaned = line.lstrip("0123456789.-) ").strip()
                    if cleaned:
                        matches.append(cleaned)

            if matches:
                return {
                    "matches": matches[:5],
                    "confidence": "high",
                    "original_input": user_input,
                    "source": "ai",
                }
        except Exception:
            pass  # Fall through to keyword matching

    # Fallback: keyword matching against curated catalog
    catalog = PROCESS_CATALOG.get(industry, [])

    if not catalog:
        return {
            "matches": [],
            "confidence": "low",
            "message": "Industry not yet mapped. Proceeding with your input directly.",
            "original_input": user_input,
        }

    # Simple keyword matching (placeholder for semantic/LLM matching)
    scored = []
    for canonical in catalog:
        canonical_lower = canonical.lower()
        user_words = set(user_lower.replace("-", " ").replace("&", " ").split())
        canonical_words = set(canonical_lower.replace("-", " ").replace("&", " ").replace("(", "").replace(")", "").split())

        overlap = user_words & canonical_words
        if overlap:
            score = len(overlap) / max(len(user_words), 1)
            scored.append({"name": canonical, "score": score})

    # Sort by score descending, take top 3
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_matches = scored[:3]

    if not top_matches:
        top_matches = [{"name": p, "score": 0.3} for p in catalog[:5]]
        confidence = "low"
    elif top_matches[0]["score"] >= 0.6:
        confidence = "high"
    else:
        confidence = "medium"

    return {
        "matches": [m["name"] for m in top_matches],
        "confidence": confidence,
        "original_input": user_input,
        "source": "catalog",
    }


def generate_parameters(confirmed_process: str, industry: str) -> list:
    """
    Generate the initial parameter universe for the rho gate.
    Returns list of parameter dicts ready for DB insertion.
    
    Architecture note: Replace with LLM API call for production (will generate
    context-aware parameters based on process + industry + client context).
    """
    # Try exact match first
    params = PARAMETER_CATALOG.get(confirmed_process, None)
    
    if params:
        return params
    
    # Fuzzy fallback: check if any catalog key is contained in confirmed_process
    confirmed_lower = confirmed_process.lower()
    for key, value in PARAMETER_CATALOG.items():
        if key.lower() in confirmed_lower or confirmed_lower in key.lower():
            return value
    
    # If nothing matches, return generic operational parameters
    return [
        {"name": "Process Cycle Time", "source": "standard", "description": "End-to-end time from trigger to completion"},
        {"name": "First-Pass Yield", "source": "standard", "description": "Percentage completed correctly without rework"},
        {"name": "Cost per Transaction", "source": "standard", "description": "Total cost divided by volume processed"},
        {"name": "Error/Defect Rate", "source": "standard", "description": "Errors per unit of output"},
        {"name": "Resource Utilization", "source": "standard", "description": "Actual vs available capacity"},
        {"name": "Customer Satisfaction Score", "source": "standard", "description": "End-user rating of process outcome"},
        {"name": "Compliance Adherence Rate", "source": "regulation", "description": "Percentage meeting regulatory requirements"},
        {"name": "Backlog Volume", "source": "standard", "description": "Pending items exceeding SLA threshold"},
        {"name": "Automation Coverage", "source": "ai", "description": "Percentage of steps with automated execution"},
        {"name": "Escalation Rate", "source": "standard", "description": "Percentage requiring management intervention"},
    ]
