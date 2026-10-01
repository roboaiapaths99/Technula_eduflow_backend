"""
School Registration & Search API.
Handles multi-tenant school onboarding and search for parent app.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models.school import SchoolDB
from models.user_db import UserDB
from auth.auth_service import hash_password, create_access_token
from auth.dependencies import require_role

router = APIRouter(prefix="/schools", tags=["Schools"])


from models.subject import Subject

# ── Request Models ────────────────────────
class SchoolRegisterRequest(BaseModel):
    name: str
    code: str | None = None
    board: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    email: str
    admin_name: str
    admin_email: str
    admin_password: str


class SchoolSearchRequest(BaseModel):
    query: str


DEFAULT_SUBJECTS = [
    ("Mathematics", "MATH", 1),
    ("Science", "SCI", 2),
    ("English Language & Lit", "ENG", 3),
    ("Social Science", "SST", 4),
    ("Second Language / Hindi", "LANG", 5),
    ("Computer Science & IT", "IT", 6),
    ("Physical Education", "PE", 7),
    ("Art & Design", "ART", 8),
]


from core.sanitizer import validate_email, validate_phone, validate_full_name, sanitize_text

# ── School Registration ──────────────────
@router.post("/register", summary="Register a new school + create admin account")
def register_school(payload: SchoolRegisterRequest, db: Session = Depends(get_db)):
    """
    1. Strictly validates school details, emails, phones, and admin identity
    2. Creates the school record
    3. Creates the admin user for that school
    4. Auto-seeds core academic subjects
    5. Returns school info + admin login token
    """
    school_name = validate_full_name(payload.name, field_name="School Name")
    school_email = validate_email(payload.email, field_name="School Email")
    admin_name = validate_full_name(payload.admin_name, field_name="Administrator Name")
    admin_email = validate_email(payload.admin_email, field_name="Administrator Email")
    clean_phone = validate_phone(payload.phone, required=False, field_name="School Phone Number") if payload.phone else None

    # Check if school email already exists
    existing = db.query(SchoolDB).filter(SchoolDB.email == school_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A school with this email already exists")

    # Check if admin email already exists
    existing_user = db.query(UserDB).filter(UserDB.email == admin_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already registered")

    # Generate or validate code
    school_code = (payload.code or "").strip().upper()
    if school_code:
        if db.query(SchoolDB).filter(func.upper(SchoolDB.code) == school_code).first():
            raise HTTPException(status_code=400, detail="This school code is already taken. Please choose another.")
    else:
        clean_name = "".join(c for c in school_name.upper() if c.isalnum())
        prefix = clean_name[:4] if len(clean_name) >= 4 else clean_name.ljust(4, "X")
        school_code = f"{prefix}01"
        idx = 1
        while db.query(SchoolDB).filter(SchoolDB.code == school_code).first():
            idx += 1
            school_code = f"{prefix}{idx:02d}"

    # Create school
    school = SchoolDB(
        code=school_code,
        name=school_name,
        board=(payload.board or "").strip() or None,
        address=(payload.address or "").strip() or None,
        city=(payload.city or "").strip() or None,
        state=(payload.state or "").strip() or None,
        phone=clean_phone,
        email=school_email,
    )
    db.add(school)
    db.flush()  # Get school.id without committing

    # Create admin user
    admin = UserDB(
        school_id=school.id,
        email=admin_email,
        full_name=admin_name,
        password_hash=hash_password(payload.admin_password),
        role="Admin",
        email_verified=True,  # Auto-verify for now
    )
    db.add(admin)

    # Seed core academic subjects for this school
    for sub_name, sub_code, sort_idx in DEFAULT_SUBJECTS:
        subj = Subject(
            school_id=school.id,
            name=sub_name,
            code=sub_code,
            sort_order=sort_idx,
        )
        db.add(subj)

    # Auto-provision 10-day free trial SaaS subscription
    from models.subscription_plan_db import SubscriptionPlanDB, PLAN_FEATURES, FREE_TRIAL_DAYS
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    trial_sub = SubscriptionPlanDB(
        school_id=school.id,
        plan_tier="starter",
        billing_cycle="monthly",
        amount=0.0,
        max_students=100,
        max_staff=5,
        features=PLAN_FEATURES["starter"],
        is_active=True,
        is_trial=True,
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=FREE_TRIAL_DAYS),
        started_at=now,
        expires_at=now + timedelta(days=FREE_TRIAL_DAYS),
    )
    db.add(trial_sub)

    db.commit()
    db.refresh(school)
    db.refresh(admin)

    # Create access token
    token = create_access_token({"sub": str(admin.id), "role": admin.role, "school_id": str(school.id)})

    return {
        "status": "ok",
        "school": {
            "id": str(school.id),
            "name": school.name,
            "board": school.board,
            "email": school.email,
        },
        "admin": {
            "id": str(admin.id),
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role,
        },
        "access_token": token,
        "token_type": "bearer",
    }


# ── School Code Resolution (for Parent App) ─────
@router.get("/by-code/{code}", summary="Get school by unique 6-character code")
def get_school_by_code(code: str, db: Session = Depends(get_db)):
    """
    Public endpoint — parents resolve a 6-character school code (e.g. DPS-DEL or TECH01).
    """
    clean_code = code.strip().upper().replace(" ", "").replace("-", "")
    schools = db.query(SchoolDB).filter(SchoolDB.is_active == True).all()
    matched = None

    # Pass 1: Exact match on clean code
    for s in schools:
        if s.code:
            s_code_clean = s.code.strip().upper().replace(" ", "").replace("-", "")
            if s_code_clean == clean_code or s.code.strip().upper() == code.strip().upper():
                matched = s
                break

    # Pass 2: Common typos / aliases (e.g. DELHI01 / DELHI0 -> DELH01, ALPHA01 -> ALPH01)
    if not matched and len(clean_code) >= 4:
        for s in schools:
            if s.code:
                s_code_clean = s.code.strip().upper().replace(" ", "").replace("-", "")
                if (clean_code.startswith(s_code_clean[:4]) or s_code_clean.startswith(clean_code[:4])):
                    matched = s
                    break

    # Pass 3: Match on school name prefix or abbreviation
    if not matched and len(clean_code) >= 3:
        for s in schools:
            clean_name = s.name.strip().upper().replace(" ", "")
            if clean_code in clean_name:
                matched = s
                break

    if not matched:
        raise HTTPException(status_code=404, detail=f"No active school found with code '{code}'. Please check with your school administration.")

    return {
        "id": str(matched.id),
        "code": matched.code,
        "name": matched.name,
        "board": matched.board,
        "city": matched.city,
        "state": matched.state,
        "phone": matched.phone,
        "email": matched.email,
        "logo_url": matched.logo_url,
    }


# ── School Search (for Parent App) ───────
@router.get("/search", summary="Search schools by name or code (for parent onboarding)")
def search_schools(q: Optional[str] = None, query: Optional[str] = None, db: Session = Depends(get_db)) -> List[dict]:
    """
    Public endpoint — parents search for their child's school by name, city, or code.
    Returns active schools matching the query.
    """
    term = (query or q or "").strip().lower()
    db_query = db.query(SchoolDB).filter(SchoolDB.is_active == True)

    if term:
        db_query = db_query.filter(
            (SchoolDB.name.ilike(f"%{term}%")) | 
            (SchoolDB.city.ilike(f"%{term}%")) |
            (SchoolDB.code.ilike(f"%{term}%"))
        )

    schools = db_query.order_by(SchoolDB.name.asc()).limit(30).all()

    return [
        {
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "board": s.board,
            "city": s.city,
            "state": s.state,
            "phone": s.phone,
            "email": s.email,
            "logo_url": s.logo_url,
        }
        for s in schools
    ]


# ── List All Active Schools ────────────────
@router.get("/all", summary="List all registered active schools")
def list_all_schools(db: Session = Depends(get_db)):
    schools = db.query(SchoolDB).filter(SchoolDB.is_active == True).order_by(SchoolDB.name.asc()).all()
    return [
        {
            "id": str(s.id),
            "code": s.code,
            "name": s.name,
            "board": s.board,
            "affiliation_no": s.affiliation_no,
            "principal_name": s.principal_name,
            "website": s.website,
            "academic_year": s.academic_year or "2025-26",
            "city": s.city,
            "state": s.state,
            "address": s.address,
            "phone": s.phone,
            "email": s.email,
            "logo_url": s.logo_url,
        }
        for s in schools
    ]


# ── Get School Details ────────────────────
@router.get("/{school_id}", summary="Get school details")
def get_school(school_id: str, db: Session = Depends(get_db)):
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id, SchoolDB.is_active == True).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    return {
        "id": str(school.id),
        "code": school.code,
        "name": school.name,
        "board": school.board,
        "affiliation_no": school.affiliation_no,
        "principal_name": school.principal_name,
        "website": school.website,
        "academic_year": school.academic_year or "2025-26",
        "address": school.address,
        "city": school.city,
        "state": school.state,
        "phone": school.phone,
        "email": school.email,
        "logo_url": school.logo_url,
        "stamp_url": getattr(school, "stamp_url", None),
        "signature_url": getattr(school, "signature_url", None),
        "is_active": school.is_active,
    }


# ── Update School Details ─────────────────
@router.put("/{school_id}", summary="Update school profile and identity")
def update_school(
    school_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    if str(user.school_id) != str(school.id):
        raise HTTPException(status_code=403, detail="Not authorized to edit another institution")

    # Handle code update with uniqueness check
    if "code" in payload and payload["code"]:
        new_code = payload["code"].strip().upper()
        if new_code != (school.code or "").upper():
            conflict = db.query(SchoolDB).filter(
                func.upper(SchoolDB.code) == new_code,
                SchoolDB.id != school.id
            ).first()
            if conflict:
                raise HTTPException(status_code=400, detail="This school code is already in use by another institution.")
            school.code = new_code

    for field in [
        "name", "board", "affiliation_no", "principal_name", "website",
        "academic_year", "address", "city", "state", "phone", "email",
        "logo_url", "stamp_url", "signature_url"
    ]:
        if field in payload and payload[field] is not None:
            setattr(school, field, payload[field])


    db.commit()
    db.refresh(school)
    return {
        "status": "ok",
        "message": "School institutional profile updated successfully",
        "school": {
            "id": str(school.id),
            "name": school.name,
            "board": school.board,
            "affiliation_no": school.affiliation_no,
            "principal_name": school.principal_name,
            "website": school.website,
            "academic_year": school.academic_year or "2025-26",
            "address": school.address,
            "city": school.city,
            "state": school.state,
            "phone": school.phone,
            "email": school.email,
            "logo_url": school.logo_url,
            "stamp_url": getattr(school, "stamp_url", None),
            "signature_url": getattr(school, "signature_url", None),
        }
    }



# ── List Classes for a School (for parent child-linking) ────
@router.get("/{school_id}/classes", summary="List available classes and sections")
def list_school_classes(school_id: str, db: Session = Depends(get_db)):
    """Returns unique grade+section combinations that have students."""
    from models.student_db import StudentDB

    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    rows = (
        db.query(StudentDB.grade, StudentDB.section)
        .filter(StudentDB.school_id == school_id, StudentDB.is_active == True)
        .distinct()
        .order_by(StudentDB.grade.asc(), StudentDB.section.asc())
        .all()
    )

    return [{"grade": r.grade, "section": r.section} for r in rows]
