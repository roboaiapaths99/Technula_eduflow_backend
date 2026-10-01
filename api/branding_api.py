"""
Branding & White-Label API — School identity, brand color, and footer attribution.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.school import SchoolDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/branding", tags=["School Branding"])


@router.get("/public/{school_id}")
def get_public_branding(
    school_id: str,
    db: Session = Depends(get_db),
):
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    return {
        "school_id": str(school.id),
        "name": school.name,
        "board": school.board,
        "logo_url": school.logo_url,
        "brand_color": getattr(school, "brand_color", "#635bff") or "#635bff",
        "powered_by_text": getattr(school, "powered_by_text", "Powered by Technula-Gaj") or "Powered by Technula-Gaj",
        "city": school.city,
        "state": school.state,
    }


@router.get("/")
def get_school_branding(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    return {
        "school_id": str(school.id),
        "name": school.name,
        "board": school.board,
        "logo_url": school.logo_url,
        "stamp_url": school.stamp_url,
        "signature_url": school.signature_url,
        "brand_color": getattr(school, "brand_color", "#635bff") or "#635bff",
        "powered_by_text": getattr(school, "powered_by_text", "Powered by Technula-Gaj") or "Powered by Technula-Gaj",
        "parent_profile_approval_required": getattr(school, "parent_profile_approval_required", False),
        "birthday_template": getattr(school, "birthday_template", None),
    }


@router.put("/")
@router.put("/{school_id}")
def update_school_branding(
    payload: dict,
    school_id: str = None,
    user: UserDB = Depends(require_role(["Admin", "Principal"])),
    db: Session = Depends(get_db),
):
    target_school_id = school_id or user.school_id
    school = db.query(SchoolDB).filter(SchoolDB.id == target_school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")

    if "brand_color" in payload:
        school.brand_color = str(payload["brand_color"]).strip()
    if "powered_by_text" in payload:
        school.powered_by_text = str(payload["powered_by_text"]).strip()
    if "logo_url" in payload:
        school.logo_url = payload["logo_url"]
    if "parent_profile_approval_required" in payload:
        school.parent_profile_approval_required = bool(payload["parent_profile_approval_required"])
    if "birthday_template" in payload:
        school.birthday_template = payload["birthday_template"]

    db.commit()
    db.refresh(school)
    return {
        "success": True,
        "message": "School branding and configuration updated.",
        "brand_color": getattr(school, "brand_color", "#635bff"),
        "powered_by_text": getattr(school, "powered_by_text", "Powered by Technula-Gaj"),
        "parent_profile_approval_required": getattr(school, "parent_profile_approval_required", False),
        "birthday_template": getattr(school, "birthday_template", None),
    }


# ── ALIAS FOR MOBILE APP: GET SCHOOL BRANDING ──────────────────────────
@router.get("/{school_id}")
def get_branding_by_school_id(
    school_id: str,
    db: Session = Depends(get_db),
):
    """Alias for mobile app: GET /branding/{school_id} → public branding."""
    return get_public_branding(school_id=school_id, db=db)

