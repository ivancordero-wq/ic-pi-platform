"""
IC-π™ Platform: Authentication Routes
======================================
Handles:
1. POST /auth/login       → Email + password login (Consultants, Admins, Leadership)
2. POST /auth/sme-access  → Magic-link token verification (SMEs)
3. GET  /auth/me          → Returns current user info from token (utility)
4. GET  /                 → Serves the login page (HTML)

After successful auth, a JWT is set as an HTTP-only cookie AND returned
in the JSON response (supports both browser and API clients).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.auth import (
    verify_password,
    create_access_token,
    decode_access_token,
    decode_magic_link_token,
    TokenData,
)

# ---------------------------------------------------------------------------
# Router Setup
# ---------------------------------------------------------------------------
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    """Email + password login payload."""
    email: str
    password: str


class SMEAccessRequest(BaseModel):
    """Magic-link token payload (pasted by SME)."""
    token: str


class AuthResponse(BaseModel):
    """Successful auth response."""
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    redirect_url: str


# ---------------------------------------------------------------------------
# Role → Redirect Mapping
# ---------------------------------------------------------------------------
ROLE_REDIRECTS = {
    "super_admin": "/admin/dashboard",
    "consultant": "/consultant/dashboard",
    "leadership": "/leadership/dashboard",
    "sme": "/sme/portal",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Serve the login screen (Screen 1).
    If user already has a valid token cookie, redirect to their dashboard.
    """
    token = request.cookies.get("access_token")
    if token:
        user_data = decode_access_token(token)
        if user_data:
            return RedirectResponse(
                url=ROLE_REDIRECTS.get(user_data.role, "/"),
                status_code=303,
            )
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate with email + password.
    Used by: Consultants, Super Admins, Leadership users.

    Returns JWT token + sets HTTP-only cookie for browser sessions.
    """
    # Find user by email
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Check if account is active
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended. Contact administrator.")

    # Create JWT
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )

    # Set HTTP-only cookie (browser sessions)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,       # HTTPS only (Railway provides TLS)
        samesite="lax",
        max_age=28800,     # 8 hours in seconds
    )

    return AuthResponse(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
        redirect_url=ROLE_REDIRECTS.get(user.role, "/"),
    )


@router.post("/auth/sme-access", response_model=AuthResponse)
async def sme_access(payload: SMEAccessRequest, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate via magic-link token (SME tab).
    Token binds SME to a specific Discovery exercise.

    SMEs typically click a magic link (which hits this endpoint automatically),
    but can also paste the token manually as a fallback.
    """
    # Decode the magic-link token
    token_data = decode_magic_link_token(payload.token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired access link")

    # Create a session token for the SME
    session_token = create_access_token(
        user_id=token_data["sme_id"],
        email=f"sme-{token_data['sme_id']}@magic-link",
        role="sme",
    )

    # Set cookie
    response.set_cookie(
        key="access_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=28800,
    )

    return AuthResponse(
        access_token=session_token,
        role="sme",
        full_name="Subject Matter Expert",
        redirect_url=f"/sme/portal?discovery={token_data['discovery_id']}",
    )


@router.get("/auth/me")
async def get_current_user(request: Request):
    """
    Utility endpoint: returns the currently authenticated user's info.
    Useful for front-end to check session status.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = decode_access_token(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Token expired or invalid")

    return {
        "user_id": user_data.user_id,
        "email": user_data.email,
        "role": user_data.role,
    }


@router.post("/auth/logout")
async def logout(response: Response):
    """Clear the auth cookie and redirect to login."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out", "redirect_url": "/"}
