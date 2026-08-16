"""
IC-Pi Platform: Seed Default Users
====================================
Creates a test consultant account on first run.
Skips if the user already exists (safe to re-run).
"""

from app.database import SessionLocal
from app.models import User
from app.auth import hash_password


def seed_default_users():
    db = SessionLocal()
    try:
        # Check if consultant already exists
        existing = db.query(User).filter(User.email == "maria@iccommerce.us").first()
        if existing:
            print("[SEED] Test consultant already exists. Skipping.")
            return

        # Create test consultant
        consultant = User(
            email="maria@iccommerce.us",
            hashed_password=hash_password("icpi2026"),
            full_name="Maria Rodriguez",
            role="consultant",
            is_active=True,
        )
        db.add(consultant)
        db.commit()
        print("[SEED] Created test consultant: maria@iccommerce.us / icpi2026")
    finally:
        db.close()
