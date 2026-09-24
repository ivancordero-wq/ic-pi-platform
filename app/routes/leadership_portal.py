"""
Screen 5: Leadership Portal
===========================
Read-only view for client leadership. Shows zone, Survival Gate status,
parameter breakdown, NPI trend across Stewardship cycles, prescriptions,
and Blueprint access.

READ-ONLY BY DESIGN: this route never recomputes and never writes. It reads
the EngineResult rows already stored by Screen 3G.

Route: /leadership/{discovery_id}
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import Discovery, Process, EngineResult
from app.auth import decode_access_token

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

LOCAL_TZ = ZoneInfo("America/Chicago")

# Confirm both against /docs before a client ever sees this page.
EXEC_SUMMARY_URL = "/blueprint/{discovery_id}/executive-summary"
FULL_BLUEPRINT_URL = "/blueprint/{discovery_id}/full"

# Trend chart plot area, inside viewBox "0 0 400 200"
PLOT_LEFT = 44.0
PLOT_RIGHT = 384.0
PLOT_TOP = 16.0
PLOT_BOTTOM = 176.0


def require_auth(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return None
    return decode_access_token(token)


def npi_to_y(value):
    """Map an NPI value (0-100) to a y coordinate in the plot area."""
    if value is None:
        return PLOT_BOTTOM
    v = max(0.0, min(100.0, float(value)))
    return round(PLOT_BOTTOM - (v / 100.0) * (PLOT_BOTTOM - PLOT_TOP), 2)


def to_local(dt):
    """Stored timestamps are naive UTC. Leadership sees local time, never UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TZ)


def sort_key(row):
    dt = row.generated_at
    if dt is None:
        return datetime(1970, 1, 1, tzinfo=ZoneInfo("UTC"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def pretty_label(label, index):
    if not label:
        return "Cycle %d" % (index + 1)
    return label.replace("_", " ").strip().capitalize()


@router.get("/leadership/{discovery_id}", response_class=HTMLResponse)
async def leadership_portal(request: Request, discovery_id: str):
    user = require_auth(request)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    db = SessionLocal()
    try:
        discovery = db.query(Discovery).filter(
            Discovery.id == discovery_id
        ).first()
        if not discovery:
            return RedirectResponse(url="/dashboard", status_code=302)

        process = db.query(Process).filter(
            Process.discovery_id == discovery.id
        ).first()

        # Client identity, defensively (schema varies by discovery vintage)
        client_obj = getattr(discovery, "client", None)
        client_name = (
            getattr(discovery, "client_name", None)
            or (getattr(client_obj, "name", None) if client_obj is not None else None)
            or "Client"
        )
        client_country = (
            getattr(discovery, "client_country", None)
            or (getattr(client_obj, "country", None) if client_obj is not None else None)
            or ""
        )

        # ---- Stored measurement history (never recomputed here) ----
        history = db.query(EngineResult).filter(
            EngineResult.discovery_id == str(discovery.id)
        ).all()
        history.sort(key=sort_key)

        points = []
        latest_data = {}
        latest_stamp = None

        for idx, row in enumerate(history):
            data = {}
            if row.result_json:
                try:
                    data = json.loads(row.result_json)
                except Exception:
                    data = {}

            npi = data.get("npi_score")
            stamp = to_local(row.generated_at)

            if len(history) == 1:
                x = round((PLOT_LEFT + PLOT_RIGHT) / 2, 2)
            else:
                span = PLOT_RIGHT - PLOT_LEFT
                x = round(PLOT_LEFT + idx * span / (len(history) - 1), 2)

            points.append({
                "label": pretty_label(row.measurement_label, idx),
                "npi": npi,
                "zone": data.get("zone") or row.overall_zone or "",
                "date": stamp.strftime("%b %d, %Y") if stamp else "",
                "x": x,
                "y": npi_to_y(npi),
                "plotted": npi is not None,
            })

            latest_data = data
            latest_stamp = stamp

        has_result = bool(latest_data)

        npi = latest_data.get("npi_score")
        zone = latest_data.get("zone") or ""
        red_floor = latest_data.get("red_floor") or 20
        green_target = latest_data.get("green_target") or 80
        alpha_alerts = latest_data.get("alpha_alerts") or []
        parameters = latest_data.get("parameter_results") or []
        ai_prescriptions = latest_data.get("ai_prescriptions") or []

        # Zone strip marker
        marker_pct = 0
        if npi is not None:
            marker_pct = max(0, min(100, round(float(npi), 1)))

        # Prescriptions grouped by tier, in escalation order
        raw_rx = latest_data.get("prescriptions") or []
        tier_order = ["CRITICAL", "HIGH IMPACT", "PREVENTIVE"]
        prescription_tiers = []
        for tier in tier_order:
            items = [p for p in raw_rx if p.get("tier") == tier]
            if items:
                prescription_tiers.append({"tier": tier, "items": items})
        leftovers = [p for p in raw_rx if p.get("tier") not in tier_order]
        if leftovers:
            prescription_tiers.append({"tier": "OTHER", "items": leftovers})

        # Trend chart geometry
        y_red = npi_to_y(red_floor)
        y_green = npi_to_y(green_target)
        bands = {
            "red_y": y_red,
            "red_h": round(PLOT_BOTTOM - y_red, 2),
            "yellow_y": y_green,
            "yellow_h": round(y_red - y_green, 2),
            "green_y": PLOT_TOP,
            "green_h": round(y_green - PLOT_TOP, 2),
            "left": PLOT_LEFT,
            "right": PLOT_RIGHT,
            "top": PLOT_TOP,
            "bottom": PLOT_BOTTOM,
            "width": round(PLOT_RIGHT - PLOT_LEFT, 2),
        }
        polyline = " ".join(
            "%s,%s" % (p["x"], p["y"]) for p in points if p["plotted"]
        )

        # Staleness
        measured_on = ""
        days_stale = None
        if latest_stamp:
            measured_on = latest_stamp.strftime("%b %d, %Y at %I:%M %p")
            days_stale = (datetime.now(LOCAL_TZ) - latest_stamp).days

        # Process selector: this client's other discoveries
        siblings = []
        client_id = getattr(discovery, "client_id", None)
        if client_id is not None:
            for d in db.query(Discovery).filter(
                Discovery.client_id == client_id
            ).all():
                p = db.query(Process).filter(
                    Process.discovery_id == d.id
                ).first()
                siblings.append({
                    "id": str(d.id),
                    "process_name": (
                        p.name if p else (getattr(d, "name", None) or "Untitled process")
                    ),
                    "current": str(d.id) == str(discovery.id),
                })
            siblings.sort(key=lambda s: s["process_name"].lower())

        return templates.TemplateResponse("leadership_portal.html", {
            "request": request,
            "discovery": discovery,
            "process": process,
            "client_name": client_name,
            "client_country": client_country,
            "has_result": has_result,
            "npi": npi,
            "zone": zone,
            "red_floor": round(float(red_floor), 1),
            "green_target": round(float(green_target), 1),
            "marker_pct": marker_pct,
            "alpha_alerts": alpha_alerts,
            "parameters": parameters,
            "prescription_tiers": prescription_tiers,
            "ai_prescriptions": ai_prescriptions,
            "points": points,
            "polyline": polyline,
            "bands": bands,
            "cycles": len(points),
            "measured_on": measured_on,
            "days_stale": days_stale,
            "siblings": siblings,
            "exec_summary_url": EXEC_SUMMARY_URL.format(
                discovery_id=str(discovery.id)
            ),
            "full_blueprint_url": FULL_BLUEPRINT_URL.format(
                discovery_id=str(discovery.id)
            ),
            "viewed_at": datetime.now(LOCAL_TZ).strftime("%b %d, %Y at %I:%M %p"),
        })
    finally:
        db.close()
