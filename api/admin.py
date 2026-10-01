"""
Admin Management API — Full CRUD operations for multi-tenant school administration.
Handles:
- School overview & settings
- Student Management (List, Add, Update, Delete, Bulk CSV)
- Faculty / Teacher Management (List, Create, Assign to Classes)
- Parent Management & Parent-Student Links
- Exam Management (Create terms, dates, total marks)
- Subject Management (Add subjects, curriculum codes)
"""
from __future__ import annotations
import csv
import io
import uuid
import logging
from datetime import date, datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Response
from sqlalchemy.orm import Session

from db.session import get_db
from models.school import SchoolDB
from models.student_db import StudentDB
from models.exam import Exam
from models.subject import Subject
from models.user_db import UserDB
from models.parent_student_db import ParentStudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.parent_link_code_db import ParentLinkCodeDB, _generate_link_code
from models.subscription_plan_db import SubscriptionPlanDB, PLAN_QUOTAS
from auth.dependencies import require_role
from auth.auth_service import hash_password
from core.sanitizer import validate_email, validate_phone, validate_full_name, sanitize_text

logger = logging.getLogger("api.admin")

router = APIRouter()


def _provision_parent_for_student(db: Session, school_id, clean_phone: str, full_name: str, student_id, relation: str = "Father") -> UserDB:
    """Safely find or provision a parent user account without colliding email unique constraints."""
    parent_user = db.query(UserDB).filter(
        UserDB.school_id == school_id,
        UserDB.phone == clean_phone
    ).first()

    if not parent_user:
        # Create unique school-scoped email to prevent collisions across schools
        school_suffix = str(school_id).replace("-", "")[:6]
        candidate_email = f"{clean_phone}.{school_suffix}@school.parent".lower()
        if db.query(UserDB).filter(UserDB.email == candidate_email).first():
            candidate_email = f"{clean_phone}.{uuid.uuid4().hex[:6]}@school.parent".lower()

        parent_user = UserDB(
            school_id=school_id,
            email=candidate_email,
            phone=clean_phone,
            full_name=full_name or f"Parent {clean_phone[-4:]}",
            password_hash=hash_password("Parent@123"),
            role="Parent",
            is_active=True,
            email_verified=True,
        )
        db.add(parent_user)
        db.flush()
    else:
        # If user exists, update generic name or enrich family name for siblings
        curr_name = (parent_user.full_name or "").strip()
        if full_name and (not curr_name or curr_name.startswith("Parent ") or "test parent" in curr_name.lower()):
            parent_user.full_name = full_name
        elif full_name and full_name.lower() not in curr_name.lower():
            parts = [p.strip() for p in curr_name.split("&")]
            if len(parts) == 1 and len(curr_name) + len(full_name) < 45:
                parent_user.full_name = f"{curr_name} & {full_name}"

    existing_link = db.query(ParentStudentDB).filter(
        ParentStudentDB.parent_user_id == parent_user.id,
        ParentStudentDB.student_id == student_id
    ).first()
    if not existing_link:
        link = ParentStudentDB(
            parent_user_id=parent_user.id,
            student_id=student_id,
            relation=relation,
            is_primary=True,
            is_verified=True,
        )
        db.add(link)
        db.flush()
    else:
        existing_link.is_verified = True
        existing_link.relation = relation

    return parent_user


# ─────────────────────────────────────────

# Faculty / Users Management
# ─────────────────────────────────────────
@router.get("/users")
def admin_list_users(
    role: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """List school users with optional search and pagination."""
    q = db.query(UserDB).filter(UserDB.school_id == user.school_id)
    if role:
        q = q.filter(UserDB.role == role)
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(UserDB.full_name.ilike(term) | UserDB.email.ilike(term) | UserDB.phone.ilike(term))

    total = q.count()
    q = q.order_by(UserDB.full_name.asc())

    if page is not None:
        eff_limit = limit or 20
        offset = (page - 1) * eff_limit
        rows = q.offset(offset).limit(eff_limit).all()
        items = [
            {
                "id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "phone": u.phone,
                "role": u.role,
                "is_active": u.is_active,
                "must_reset_password": getattr(u, "must_reset_password", False),
                "permissions": u.permissions if hasattr(u, "permissions") else {},
            }
            for u in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    rows = q.all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "phone": u.phone,
            "role": u.role,
            "is_active": u.is_active,
            "must_reset_password": getattr(u, "must_reset_password", False),
            "permissions": u.permissions if hasattr(u, "permissions") else {},
        }
        for u in rows
    ]


@router.get("/roles")
def admin_get_available_roles(
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """List standard roles plus any custom roles created in this school."""
    standard_roles = [
        "Teacher",
        "ClassTeacher",
        "SubjectTeacher",
        "Accountant",
        "Librarian",
        "Counselor",
        "Staff",
        "Admin",
    ]
    # Fetch distinct custom roles existing in this school
    custom_roles = (
        db.query(UserDB.role)
        .filter(UserDB.school_id == user.school_id, UserDB.role.isnot(None))
        .distinct()
        .all()
    )
    existing_roles = {r[0] for r in custom_roles if r[0] and r[0] not in ["SuperAdmin", "Parent"]}
    all_roles = sorted(list(set(standard_roles).union(existing_roles)))
    return {"roles": all_roles, "standard_roles": standard_roles}


@router.post("/users")
def admin_create_user(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin invites/creates a new teacher, staff, custom role, or parent with quota enforcement."""
    raw_email = (payload.get("email") or "").strip().lower()
    email = validate_email(raw_email, field_name="Staff Email")
    password = payload.get("password") or "School@123"
    role = (payload.get("role") or "Teacher").strip()
    full_name = validate_full_name(payload.get("full_name"), field_name="Staff Full Name")
    raw_phone = (payload.get("phone") or "").strip() or None
    phone = validate_phone(raw_phone, required=False, field_name="Staff Phone Number") if raw_phone else None
    if role.lower() == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot assign SuperAdmin role")

    # Staff Quota Enforcement (Non-Parent accounts count towards staff limit)
    if role != "Parent":
        sub = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.school_id == user.school_id
        ).first()
        max_staff = sub.max_staff if sub else PLAN_QUOTAS["starter"]["max_staff"]
        current_staff = db.query(UserDB).filter(
            UserDB.school_id == user.school_id,
            UserDB.role != "Parent",
        ).count()

        if current_staff >= max_staff:
            raise HTTPException(
                status_code=403,
                detail=f"Staff limit reached ({current_staff}/{max_staff}). Please upgrade your subscription plan to add more staff.",
            )

    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    # Build permissions from payload or use defaults
    import json as _json
    from models.user_db import DEFAULT_STAFF_PERMISSIONS
    perms = payload.get("permissions") or {}
    if role.lower() == "admin":
        perms_final = {k: True for k in DEFAULT_STAFF_PERMISSIONS}
    else:
        perms_final = {**DEFAULT_STAFF_PERMISSIONS, **perms}

    new_u = UserDB(
        school_id=user.school_id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
        role=role,
        is_active=True,
        email_verified=True,
        must_reset_password=True,  # Force password change on first login
        permissions_json=_json.dumps(perms_final),
    )
    db.add(new_u)
    db.commit()
    db.refresh(new_u)

    # Dispatch credential email to new staff member
    try:
        from services.notification_service import send_email
        school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
        school_name = school.name if school else "Your School"
        send_email(
            to_email=email,
            subject=f"Welcome to {school_name} — Your Login Credentials",
            html_content=f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: auto; padding: 32px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff;">
                <h2 style="color: #635bff; margin-top: 0;">Welcome to {school_name}!</h2>
                <p style="font-size: 15px; color: #334155; line-height: 1.6;">Hello <strong>{full_name}</strong>,</p>
                <p style="font-size: 15px; color: #334155; line-height: 1.6;">Your {role} account has been created. Here are your login credentials:</p>
                <div style="background: #f8fafc; padding: 16px; border-radius: 8px; margin: 16px 0;">
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Email:</strong> {email}</p>
                    <p style="margin: 4px 0; font-size: 14px;"><strong>Temporary Password:</strong> {password}</p>
                </div>
                <p style="font-size: 14px; color: #ef4444; font-weight: 600;">⚠️ You will be required to change your password upon first login.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                <p style="font-size: 12px; color: #94a3b8;">Academic Insights AI — {school_name}</p>
            </div>
            """,
        )
    except Exception:
        pass  # Email dispatch is best-effort; don't fail user creation

    return {
        "status": "ok",
        "user": {
            "id": str(new_u.id),
            "email": new_u.email,
            "full_name": new_u.full_name,
            "role": new_u.role,
            "phone": new_u.phone,
            "is_active": new_u.is_active,
            "must_reset_password": True,
            "permissions": perms_final,
        },
    }


@router.put("/users/{user_id}")
def admin_update_user(
    user_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin updates faculty or staff details, role, or active status."""
    target = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.school_id == user.school_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your school")

    if "full_name" in payload and payload["full_name"]:
        target.full_name = payload["full_name"].strip()
    if "phone" in payload:
        target.phone = (payload["phone"] or "").strip() or None
    if "role" in payload and payload["role"]:
        new_role = payload["role"].strip()
        if new_role.lower() == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot assign SuperAdmin role")
        target.role = new_role
    if "is_active" in payload:
        target.is_active = bool(payload["is_active"])

    if "permissions" in payload and isinstance(payload["permissions"], dict):
        import json as _json
        target.permissions_json = _json.dumps(payload["permissions"])

    db.commit()
    db.refresh(target)

    return {
        "status": "ok",
        "user": {
            "id": str(target.id),
            "email": target.email,
            "full_name": target.full_name,
            "role": target.role,
            "phone": target.phone,
            "is_active": target.is_active,
            "must_reset_password": getattr(target, "must_reset_password", False),
            "permissions": target.permissions if hasattr(target, "permissions") else {},
        },
    }


@router.post("/users/{user_id}/reset-password")
def admin_reset_user_password(
    user_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin resets a staff or user's password and forces change on next login."""
    target = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.school_id == user.school_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your school")

    new_password = payload.get("password") or "School@123"
    target.password_hash = hash_password(new_password)
    target.must_reset_password = True
    db.commit()

    # Dispatch email alert if configured
    try:
        from services.notification_service import send_email
        school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
        school_name = school.name if school else "Your School"
        email_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; color: #1e293b; max-width: 600px;">
            <h2 style="color: #2563eb;">Password Reset Notice</h2>
            <p>Dear {target.full_name},</p>
            <p>Your password for <strong>{school_name}</strong> portal has been reset by the school administrator.</p>
            <div style="background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>Login Email:</strong> {target.email}</p>
                <p style="margin: 0;"><strong>Temporary Password:</strong> <code style="background: #e2e8f0; padding: 2px 6px; border-radius: 4px;">{new_password}</code></p>
            </div>
            <p>Upon your next login, you will be prompted to choose a new permanent password.</p>
        </div>
        """
        send_email(to_email=target.email, subject=f"Your Password for {school_name} has been reset", html_content=email_html)
    except Exception as e:
        print(f"[AdminResetPass] Notice: {e}")

    return {
        "status": "ok",
        "message": f"Password for {target.email} has been reset to temporary password. User will be forced to change it on next login.",
    }


@router.post("/users/{user_id}/send-credentials")
def admin_send_user_credentials(
    user_id: str,
    payload: Optional[dict] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin dispatches institutional login credentials to staff/teacher via email."""
    target = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.school_id == user.school_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your school")

    payload = payload or {}
    temp_password = payload.get("password") or "Staff@123"
    target.password_hash = hash_password(temp_password)
    target.must_reset_password = True
    db.commit()

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    school_name = school.name if school else "Institutional Portal"

    try:
        from services.notification_service import send_email
        email_html = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; padding: 24px; color: #0f172a; max-width: 600px; border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;">
            <div style="border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 18px;">
                <h2 style="color: #1e3a8a; margin: 0;">🏫 {school_name}</h2>
                <span style="color: #64748b; font-size: 13px;">Faculty & Staff Institutional Access</span>
            </div>
            <p style="font-size: 15px;">Dear <strong>{target.full_name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.5; color: #334155;">
                Your faculty account on the {school_name} management platform is active. You have been provisioned with the <strong>{target.role}</strong> role.
            </p>
            <div style="background: #f1f5f9; padding: 18px; border-radius: 8px; margin: 20px 0; border: 1px solid #cbd5e1;">
                <div style="margin-bottom: 10px; font-size: 14px;"><strong>Portal User:</strong> {target.email}</div>
                <div style="font-size: 14px;"><strong>Temporary Password:</strong> <span style="background: #ffffff; padding: 3px 8px; border-radius: 4px; font-family: monospace; font-size: 15px; font-weight: 700; border: 1px solid #94a3b8; color: #1e293b;">{temp_password}</span></div>
            </div>
            <p style="font-size: 13px; color: #64748b; line-height: 1.5;">
                🔒 <strong>Security Note:</strong> On your first sign in, you will be required to create your own secure, permanent password before accessing school records.
            </p>
            <div style="margin-top: 24px;">
                <a href="http://localhost:5173" style="background: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: 700; display: inline-block; font-size: 14px;">Log In to School Portal &rarr;</a>
            </div>
        </div>
        """
        send_email(
            to_email=target.email,
            subject=f"Welcome to {school_name} — Your Staff Login Credentials",
            html_content=email_html
        )
        email_dispatched = True
    except Exception as e:
        logger.warning(f"Failed to dispatch credentials email to {target.email}: {e}")
        email_dispatched = False

    return {
        "status": "ok",
        "email_dispatched": email_dispatched,
        "message": f"Credentials dispatched to {target.email}. Temporary password set to '{temp_password}'.",
    }


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin deletes or deactivates a user from their school."""
    if str(user.id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

    target = db.query(UserDB).filter(
        UserDB.id == user_id,
        UserDB.school_id == user.school_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your school")

    db.delete(target)
    db.commit()

    return {"status": "ok", "message": "User deleted successfully"}


# ─────────────────────────────────────────
# Student Management CRUD
# ─────────────────────────────────────────
@router.get("/students")
def admin_list_students(
    grade: Optional[str] = None,
    section: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    q = db.query(StudentDB).filter(StudentDB.school_id == user.school_id, StudentDB.is_active == True)
    if grade:
        q = q.filter(StudentDB.grade == grade)
    if section:
        q = q.filter(StudentDB.section == section)
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            StudentDB.name.ilike(term) |
            StudentDB.admission_no.ilike(term) |
            StudentDB.roll_no.ilike(term) |
            StudentDB.father_phone.ilike(term) |
            StudentDB.mother_phone.ilike(term)
        )

    total = q.count()
    q = q.order_by(StudentDB.grade.asc(), StudentDB.section.asc(), StudentDB.roll_no.asc())

    if page is not None:
        eff_limit = limit or 25
        offset = (page - 1) * eff_limit
        rows = q.offset(offset).limit(eff_limit).all()
        items = [
            {
                "id": str(s.id),
                "name": s.name,
                "admission_no": s.admission_no,
                "roll_no": s.roll_no,
                "grade": s.grade,
                "section": s.section,
                "gender": s.gender,
                "dob": s.dob.isoformat() if s.dob else None,
                "photo_url": s.photo_url,
                "father_name": s.father_name,
                "father_phone": s.father_phone,
                "mother_name": s.mother_name,
                "mother_phone": s.mother_phone,
                "blood_group": s.blood_group,
                "emergency_contact_name": s.emergency_contact_name,
                "emergency_contact_phone": s.emergency_contact_phone,
                "address": s.address,
                "medical_notes": s.medical_notes,
                "previous_school": s.previous_school,
                "is_active": s.is_active,
            }
            for s in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    rows = q.all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "admission_no": s.admission_no,
            "roll_no": s.roll_no,
            "grade": s.grade,
            "section": s.section,
            "gender": s.gender,
            "dob": s.dob.isoformat() if s.dob else None,
            "photo_url": s.photo_url,
            "father_name": s.father_name,
            "father_phone": s.father_phone,
            "mother_name": s.mother_name,
            "mother_phone": s.mother_phone,
            "blood_group": s.blood_group,
            "emergency_contact_name": s.emergency_contact_name,
            "emergency_contact_phone": s.emergency_contact_phone,
            "address": s.address,
            "medical_notes": s.medical_notes,
            "previous_school": s.previous_school,
            "is_active": s.is_active,
        }
        for s in rows
    ]


@router.get("/students/csv-template")
def admin_download_student_csv_template():
    """Download standard CSV template for bulk student upload."""
    csv_header = "name,admission_no,grade,section,roll_no,gender,dob,father_name,father_phone,mother_name,mother_phone,blood_group,address,emergency_contact_name,emergency_contact_phone\n"
    sample_row = "Aarav Sharma,SCH-2025-001,10,A,1,Male,2010-05-15,Rajesh Sharma,9876543210,Sunita Sharma,9876543211,B+,123 Civil Lines Delhi,Rajesh Sharma,9876543210\n"
    content = csv_header + sample_row
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_upload_template.csv"},
    )


@router.get("/students/{student_id}")
def admin_get_student_detail(
    student_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    st = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "id": str(st.id),
        "name": st.name,
        "admission_no": st.admission_no,
        "roll_no": st.roll_no,
        "grade": st.grade,
        "section": st.section,
        "gender": st.gender,
        "dob": st.dob.isoformat() if st.dob else None,
        "photo_url": st.photo_url,
        "blood_group": st.blood_group,
        "father_name": st.father_name,
        "father_phone": st.father_phone,
        "mother_name": st.mother_name,
        "mother_phone": st.mother_phone,
        "emergency_contact_name": st.emergency_contact_name,
        "emergency_contact_phone": st.emergency_contact_phone,
        "address": st.address,
        "medical_notes": st.medical_notes,
        "previous_school": st.previous_school,
        "is_active": st.is_active,
        "created_at": st.created_at.isoformat() if st.created_at else None,
    }


@router.post("/students")
def admin_create_student(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    raw_name = (payload.get("name") or "").strip()
    name = validate_full_name(raw_name, field_name="Student Name")
    admission_no = (payload.get("admission_no") or "").strip()
    grade = (payload.get("grade") or "").strip()
    section = (payload.get("section") or "").strip().upper()
    roll_no = (payload.get("roll_no") or "").strip() or None
    gender = payload.get("gender") or "Male"

    # Profile & Health Details
    photo_url = payload.get("photo_url")
    blood_group = payload.get("blood_group")
    father_name = validate_full_name(payload.get("father_name"), field_name="Father Name") if payload.get("father_name") else None
    father_phone = validate_phone(payload.get("father_phone"), required=False, field_name="Father Phone") if payload.get("father_phone") else None
    mother_name = validate_full_name(payload.get("mother_name"), field_name="Mother Name") if payload.get("mother_name") else None
    mother_phone = validate_phone(payload.get("mother_phone"), required=False, field_name="Mother Phone") if payload.get("mother_phone") else None
    emergency_contact_name = validate_full_name(payload.get("emergency_contact_name"), field_name="Emergency Contact Name") if payload.get("emergency_contact_name") else None
    emergency_contact_phone = validate_phone(payload.get("emergency_contact_phone"), required=False, field_name="Emergency Contact Phone") if payload.get("emergency_contact_phone") else None
    address = payload.get("address")
    medical_notes = payload.get("medical_notes")
    previous_school = payload.get("previous_school")
    is_active = payload.get("is_active", True)

    dob_val = payload.get("dob")
    parsed_dob = None
    if dob_val:
        try:
            if isinstance(dob_val, str) and dob_val.strip():
                parsed_dob = date.fromisoformat(dob_val.strip().split("T")[0])
        except Exception:
            parsed_dob = None

    if not name or not admission_no or not grade or not section:
        raise HTTPException(status_code=400, detail="Name, admission number, grade, and section are required")

    # Check Student Quota
    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()
    max_students = sub.max_students if sub else PLAN_QUOTAS["starter"]["max_students"]
    current_students = db.query(StudentDB).filter(
        StudentDB.school_id == user.school_id,
        StudentDB.is_active == True,
    ).count()

    if current_students >= max_students:
        raise HTTPException(
            status_code=403,
            detail=f"Student quota reached ({current_students}/{max_students}). Please upgrade your subscription plan to enroll more students.",
        )

    exists = db.query(StudentDB).filter(
        StudentDB.school_id == user.school_id,
        StudentDB.admission_no == admission_no
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="A student with this admission number already exists")

    st = StudentDB(
        school_id=user.school_id,
        name=name,
        admission_no=admission_no,
        roll_no=roll_no,
        grade=grade,
        section=section,
        gender=gender,
        dob=parsed_dob,
        photo_url=photo_url,
        blood_group=blood_group,
        father_name=father_name,
        father_phone=father_phone,
        mother_name=mother_name,
        mother_phone=mother_phone,
        emergency_contact_name=emergency_contact_name,
        emergency_contact_phone=emergency_contact_phone,
        address=address,
        medical_notes=medical_notes,
        previous_school=previous_school,
        is_active=is_active,
    )
    db.add(st)
    db.commit()
    db.refresh(st)

    # Auto-generate unique Parent Link Code
    link_code_obj = ParentLinkCodeDB(
        school_id=user.school_id,
        student_id=st.id,
        code=_generate_link_code(),
        relation="Guardian",
    )
    db.add(link_code_obj)
    db.commit()
    db.refresh(link_code_obj)

    # Auto-provision parent account(s) if father_phone or mother_phone is provided
    phones_to_provision = []
    clean_f = "".join(filter(str.isdigit, str(father_phone or "")))
    if len(clean_f) >= 10:
        phones_to_provision.append((clean_f, father_name or f"{name}'s Father", "Father"))

    clean_m = "".join(filter(str.isdigit, str(mother_phone or "")))
    if len(clean_m) >= 10 and clean_m != clean_f:
        phones_to_provision.append((clean_m, mother_name or f"{name}'s Mother", "Mother"))

    for clean_p, p_name, rel in phones_to_provision:
        try:
            _provision_parent_for_student(
                db=db,
                school_id=user.school_id,
                clean_phone=clean_p,
                full_name=p_name,
                student_id=st.id,
                relation=rel,
            )
            db.commit()
        except Exception as e:
            logger.warning(f"Parent auto-provisioning warning ({rel}): {e}")
            db.rollback()

    return {
        "status": "ok",
        "student": {
            "id": str(st.id),
            "name": st.name,
            "admission_no": st.admission_no,
            "roll_no": st.roll_no,
            "grade": st.grade,
            "section": st.section,
            "gender": st.gender,
            "dob": st.dob.isoformat() if st.dob else None,
            "photo_url": st.photo_url,
            "blood_group": st.blood_group,
            "father_name": st.father_name,
            "father_phone": st.father_phone,
            "mother_name": st.mother_name,
            "mother_phone": st.mother_phone,
            "emergency_contact_name": st.emergency_contact_name,
            "emergency_contact_phone": st.emergency_contact_phone,
            "address": st.address,
            "medical_notes": st.medical_notes,
            "previous_school": st.previous_school,
            "is_active": st.is_active,
            "parent_link_code": link_code_obj.code,
        },
    }


@router.post("/students/upload-csv")
async def admin_upload_students_csv(
    file: UploadFile = File(...),
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Bulk student CSV upload. Validates schema, checks subscription student quota,
    creates student records, and auto-generates secure parent link codes.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    content_bytes = await file.read()
    try:
        text_content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text_content = content_bytes.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to decode CSV file. Please use UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text_content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV file")

    required_fields = ["name", "admission_no", "grade", "section"]
    missing_fields = [f for f in required_fields if f not in [col.strip().lower() for col in reader.fieldnames]]
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"CSV missing required columns: {', '.join(missing_fields)}. Required: name, admission_no, grade, section",
        )

    # Normalize column mapping
    col_map = {col.strip().lower(): col for col in reader.fieldnames}

    # Fetch Quota
    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()
    max_students = sub.max_students if sub else PLAN_QUOTAS["starter"]["max_students"]
    current_students = db.query(StudentDB).filter(
        StudentDB.school_id == user.school_id,
        StudentDB.is_active == True,
    ).count()

    available_slots = max(0, max_students - current_students)
    if available_slots <= 0:
        raise HTTPException(
            status_code=403,
            detail=f"Student quota reached ({current_students}/{max_students}). Upgrade your plan to upload more students.",
        )

    created_students = []
    skipped_records = []
    errors = []

    rows = list(reader)
    for idx, row in enumerate(rows, start=2):
        name = (row.get(col_map.get("name", "")) or "").strip()
        admission_no = (row.get(col_map.get("admission_no", "")) or "").strip()
        grade = (row.get(col_map.get("grade", "")) or "").strip()
        section = (row.get(col_map.get("section", "")) or "").strip().upper()

        if not name or not admission_no or not grade or not section:
            errors.append(f"Row {idx}: Missing name, admission_no, grade, or section")
            continue

        if len(created_students) >= available_slots:
            skipped_records.append({
                "row": idx,
                "admission_no": admission_no,
                "name": name,
                "reason": f"Plan student quota of {max_students} reached. Upgrade plan for more capacity.",
            })
            continue

        # Check existing admission_no in this school
        existing = db.query(StudentDB).filter(
            StudentDB.school_id == user.school_id,
            StudentDB.admission_no == admission_no,
        ).first()

        if existing:
            skipped_records.append({
                "row": idx,
                "admission_no": admission_no,
                "name": name,
                "reason": "Admission number already exists in school",
            })
            continue

        # Parse optional fields
        roll_no = (row.get(col_map.get("roll_no", "")) or "").strip() or None
        gender = (row.get(col_map.get("gender", "")) or "Male").strip().capitalize()
        dob_raw = (row.get(col_map.get("dob", "")) or "").strip()
        parsed_dob = None
        if dob_raw:
            try:
                parsed_dob = date.fromisoformat(dob_raw.split("T")[0])
            except Exception:
                parsed_dob = None

        father_name = (row.get(col_map.get("father_name", "")) or "").strip() or None
        father_phone = (row.get(col_map.get("father_phone", "")) or "").strip() or None
        mother_name = (row.get(col_map.get("mother_name", "")) or "").strip() or None
        mother_phone = (row.get(col_map.get("mother_phone", "")) or "").strip() or None
        blood_group = (row.get(col_map.get("blood_group", "")) or "").strip() or None
        address = (row.get(col_map.get("address", "")) or "").strip() or None
        emergency_contact_name = (row.get(col_map.get("emergency_contact_name", "")) or "").strip() or None
        emergency_contact_phone = (row.get(col_map.get("emergency_contact_phone", "")) or "").strip() or None

        st = StudentDB(
            school_id=user.school_id,
            name=name,
            admission_no=admission_no,
            roll_no=roll_no,
            grade=grade,
            section=section,
            gender=gender,
            dob=parsed_dob,
            father_name=father_name,
            father_phone=father_phone,
            mother_name=mother_name,
            mother_phone=mother_phone,
            blood_group=blood_group,
            address=address,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
            is_active=True,
        )
        db.add(st)
        db.flush()

        # Create unique Parent Link Code
        link_code_obj = ParentLinkCodeDB(
            school_id=user.school_id,
            student_id=st.id,
            code=_generate_link_code(),
            relation="Guardian",
        )
        db.add(link_code_obj)
        db.flush()

        # Auto-provision parent account if phone provided
        parent_phone = father_phone or mother_phone
        if parent_phone:
            clean_phone = "".join(filter(str.isdigit, str(parent_phone)))
            if len(clean_phone) >= 10:
                rel = "Father" if father_phone else "Mother"
                p_name = father_name or mother_name or f"{name}'s Parent"
                _provision_parent_for_student(
                    db=db,
                    school_id=user.school_id,
                    clean_phone=clean_phone,
                    full_name=p_name,
                    student_id=st.id,
                    relation=rel,
                )

        created_students.append({
            "id": str(st.id),
            "name": st.name,
            "admission_no": st.admission_no,
            "grade": st.grade,
            "section": st.section,
            "parent_link_code": link_code_obj.code,
        })

    db.commit()

    return {
        "status": "ok",
        "total_in_file": len(rows),
        "created_count": len(created_students),
        "skipped_count": len(skipped_records),
        "error_count": len(errors),
        "created_students": created_students,
        "skipped_records": skipped_records,
        "errors": errors,
        "quota_remaining": max(0, available_slots - len(created_students)),
    }


@router.put("/students/{student_id}")
def admin_update_student(
    student_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    st = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")

    for field in [
        "name", "grade", "section", "roll_no", "gender", "photo_url", "blood_group",
        "father_name", "father_phone", "mother_name", "mother_phone",
        "emergency_contact_name", "emergency_contact_phone", "address",
        "medical_notes", "previous_school", "is_active"
    ]:
        if field in payload and payload[field] is not None:
            val = payload[field]
            if field in ["father_phone", "mother_phone", "emergency_contact_phone"] and val:
                val = validate_phone(val, required=False, field_name=field.replace("_", " ").title())
            elif field in ["name", "father_name", "mother_name"] and val:
                val = validate_full_name(val, field_name=field.replace("_", " ").title())
            setattr(st, field, val)

    if "dob" in payload:
        dob_val = payload.get("dob")
        if dob_val:
            try:
                st.dob = date.fromisoformat(str(dob_val).strip().split("T")[0])
            except Exception:
                pass
        else:
            st.dob = None

    db.commit()
    db.refresh(st)
    return {
        "status": "ok",
        "message": "Student updated successfully",
        "student": {
            "id": str(st.id),
            "name": st.name,
            "admission_no": st.admission_no,
            "roll_no": st.roll_no,
            "grade": st.grade,
            "section": st.section,
            "gender": st.gender,
            "dob": st.dob.isoformat() if st.dob else None,
            "photo_url": st.photo_url,
            "blood_group": st.blood_group,
            "father_name": st.father_name,
            "father_phone": st.father_phone,
            "mother_name": st.mother_name,
            "mother_phone": st.mother_phone,
            "emergency_contact_name": st.emergency_contact_name,
            "emergency_contact_phone": st.emergency_contact_phone,
            "address": st.address,
            "medical_notes": st.medical_notes,
            "previous_school": st.previous_school,
            "is_active": st.is_active,
        }
    }


@router.delete("/students/{student_id}")
def admin_delete_student(
    student_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    st = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == user.school_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")

    db.delete(st)
    db.commit()
    return {"status": "ok", "message": "Student deleted"}


# ── 2-Stage Bulk Import Engine ───────────────────────────────
@router.post("/students/bulk-validate")
def admin_bulk_validate_students(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Stage 1: Dry-run validation of student rows without writing to DB.
    Checks required fields, duplicate admission numbers in batch and against existing school records.
    """
    rows = payload.get("rows", [])
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided for validation")

    existing_admissions = set(
        adm[0] for adm in db.query(StudentDB.admission_no).filter(
            StudentDB.school_id == user.school_id
        ).all()
    )

    seen_in_batch = set()
    valid_rows = []
    errors = []

    for idx, row in enumerate(rows):
        row_num = idx + 1
        name = str(row.get("name") or "").strip()
        admission_no = str(row.get("admission_no") or "").strip()
        grade = str(row.get("grade") or "").strip()
        section = str(row.get("section") or "A").strip().upper()

        row_errors = []
        if not name:
            row_errors.append("Student Name is required")
        if not admission_no:
            row_errors.append("Admission Number is required")
        if not grade:
            row_errors.append("Grade / Class is required")

        if admission_no:
            if admission_no in existing_admissions:
                row_errors.append(f"Admission number '{admission_no}' already exists in this school")
            elif admission_no in seen_in_batch:
                row_errors.append(f"Duplicate admission number '{admission_no}' found in the import file")
            else:
                seen_in_batch.add(admission_no)

        parent_phone = str(row.get("parent_phone") or row.get("father_phone") or "").strip()
        if parent_phone:
            clean_digits = "".join(filter(str.isdigit, parent_phone))
            if len(clean_digits) < 10:
                row_errors.append(f"Invalid parent phone '{parent_phone}' (minimum 10 digits required)")

        if row_errors:
            errors.append({
                "row": row_num,
                "admission_no": admission_no or "N/A",
                "name": name or "N/A",
                "errors": row_errors,
            })
        else:
            valid_rows.append({
                "name": name,
                "admission_no": admission_no,
                "grade": grade,
                "section": section,
                "roll_no": str(row.get("roll_no") or "").strip() or None,
                "gender": str(row.get("gender") or "Male").capitalize(),
                "father_name": str(row.get("father_name") or "").strip() or None,
                "father_phone": parent_phone or None,
                "mother_name": str(row.get("mother_name") or "").strip() or None,
                "blood_group": str(row.get("blood_group") or "").strip() or None,
                "address": str(row.get("address") or "").strip() or None,
            })

    return {
        "total_rows": len(rows),
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "valid_rows": valid_rows,
        "errors": errors,
    }


@router.post("/students/bulk-commit")
def admin_bulk_commit_students(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Stage 2: Transactional commit of validated students.
    Creates students and auto-provisions parent user accounts.
    """
    valid_rows = payload.get("rows", [])
    if not valid_rows:
        raise HTTPException(status_code=400, detail="No valid rows provided for commit")

    inserted_count = 0
    parents_created = 0

    try:
        for r in valid_rows:
            st = StudentDB(
                school_id=user.school_id,
                name=r["name"],
                admission_no=r["admission_no"],
                grade=r["grade"],
                section=r["section"],
                roll_no=r.get("roll_no"),
                gender=r.get("gender", "Male"),
                father_name=r.get("father_name"),
                father_phone=r.get("father_phone"),
                mother_name=r.get("mother_name"),
                blood_group=r.get("blood_group"),
                address=r.get("address"),
                is_active=True,
            )
            db.add(st)
            db.flush()
            inserted_count += 1

            # Auto-provision parent account(s)
            p_phone = r.get("father_phone")
            m_phone = r.get("mother_phone")
            clean_f = "".join(filter(str.isdigit, str(p_phone or "")))
            clean_m = "".join(filter(str.isdigit, str(m_phone or "")))

            if len(clean_f) >= 10:
                p_name = r.get("father_name") or f"{r['name']}'s Father"
                _provision_parent_for_student(
                    db=db,
                    school_id=user.school_id,
                    clean_phone=clean_f,
                    full_name=p_name,
                    student_id=st.id,
                    relation="Father",
                )
                parents_created += 1

            if len(clean_m) >= 10 and clean_m != clean_f:
                m_name = r.get("mother_name") or f"{r['name']}'s Mother"
                _provision_parent_for_student(
                    db=db,
                    school_id=user.school_id,
                    clean_phone=clean_m,
                    full_name=m_name,
                    student_id=st.id,
                    relation="Mother",
                )
                parents_created += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database commit failed: {str(e)}")

    return {
        "status": "ok",
        "inserted_students": inserted_count,
        "provisioned_parents": parents_created,
        "message": f"Successfully enrolled {inserted_count} students and provisioned {parents_created} parent accounts!"
    }


# ─────────────────────────────────────────
# Bulk Faculty / Staff Ingestion
# ─────────────────────────────────────────
@router.get("/faculty/csv-template")
def admin_download_faculty_csv_template():
    """Download standard CSV template for bulk faculty & staff upload."""
    csv_header = "full_name,email,phone,role,assigned_grade,assigned_section,subject_name\n"
    sample_rows = (
        "Dr. Sunita Sharma,sunita.sharma@school.edu,9812345678,Teacher,10,A,Mathematics\n"
        "Rajesh Verma,rajesh.verma@school.edu,9823456789,ClassTeacher,9,B,Science\n"
        "Anita Desai,anita.desai@school.edu,9834567890,Teacher,11,A,English\n"
        "Manoj Gupta,manoj.gupta@school.edu,9845678901,Teacher,8,C,Social Science\n"
        "Priya Nair,priya.nair@school.edu,9856789012,SubjectTeacher,12,A,Physics\n"
        "Vikram Malhotra,vikram.m@school.edu,9867890123,Accountant,,,\n"
        "Kavita Joshi,kavita.j@school.edu,9878901234,Librarian,,,\n"
    )
    content = csv_header + sample_rows
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=faculty_upload_template.csv"},
    )


@router.post("/faculty/bulk-preview")
def admin_bulk_preview_faculty(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Stage 1: Dry-run validation of faculty/staff rows without writing to DB.
    Validates required fields, email format and uniqueness, phone numbers, and checks Staff Quota.
    """
    rows = payload.get("rows", [])
    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided for validation")

    # Fetch Staff Subscription Quota
    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()
    max_staff = sub.max_staff if sub else PLAN_QUOTAS["starter"]["max_staff"]
    current_staff = db.query(UserDB).filter(
        UserDB.school_id == user.school_id,
        UserDB.role != "Parent",
    ).count()
    available_slots = max(0, max_staff - current_staff)

    existing_emails = set(
        em[0].lower() for em in db.query(UserDB.email).all() if em[0]
    )

    seen_in_batch = set()
    valid_rows = []
    errors = []

    for idx, row in enumerate(rows):
        row_num = idx + 1
        raw_name = str(row.get("full_name") or row.get("name") or "").strip()
        raw_email = str(row.get("email") or "").strip().lower()
        raw_phone = str(row.get("phone") or row.get("contact") or row.get("mobile") or "").strip()
        raw_role = str(row.get("role") or row.get("designation") or "Teacher").strip()
        assigned_grade = str(row.get("assigned_grade") or row.get("grade") or "").strip()
        assigned_section = str(row.get("assigned_section") or row.get("section") or "").strip().upper()
        subject_name = str(row.get("subject_name") or row.get("subject") or "").strip()

        row_errors = []

        # Validate Name
        try:
            full_name = validate_full_name(raw_name, field_name="Faculty Full Name")
        except HTTPException as he:
            row_errors.append(he.detail)
            full_name = raw_name

        # Validate Email
        if not raw_email:
            row_errors.append("Email address is required")
        else:
            try:
                email = validate_email(raw_email, field_name="Faculty Email")
                if email in existing_emails:
                    row_errors.append(f"Email '{email}' is already registered in the system")
                elif email in seen_in_batch:
                    row_errors.append(f"Duplicate email '{email}' in this import file")
                else:
                    seen_in_batch.add(email)
            except HTTPException as he:
                row_errors.append(he.detail)
                email = raw_email

        # Validate Phone
        phone = None
        if raw_phone:
            try:
                phone = validate_phone(raw_phone, required=True, field_name="Contact Number")
            except HTTPException as he:
                row_errors.append(he.detail)

        # Standardize Role
        allowed_roles = ["Teacher", "ClassTeacher", "SubjectTeacher", "Staff", "Accountant", "Librarian", "Counselor", "Admin"]
        role = raw_role if raw_role in allowed_roles else "Teacher"

        if row_errors:
            errors.append({
                "row": row_num,
                "name": raw_name or "N/A",
                "email": raw_email or "N/A",
                "errors": row_errors,
            })
        else:
            valid_rows.append({
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "role": role,
                "assigned_grade": assigned_grade or None,
                "assigned_section": assigned_section or None,
                "subject_name": subject_name or None,
            })

    return {
        "total_rows": len(rows),
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "max_staff": max_staff,
        "current_staff": current_staff,
        "available_slots": available_slots,
        "exceeds_quota": len(valid_rows) > available_slots,
        "valid_rows": valid_rows,
        "errors": errors,
    }


@router.post("/faculty/bulk-commit")
def admin_bulk_commit_faculty(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Stage 2: Transactional commit of validated faculty & staff.
    Creates UserDB accounts, default credentials, and optional class/subject assignments.
    """
    valid_rows = payload.get("rows", [])
    if not valid_rows:
        raise HTTPException(status_code=400, detail="No valid rows provided for commit")

    # Staff Quota Enforcement
    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()
    max_staff = sub.max_staff if sub else PLAN_QUOTAS["starter"]["max_staff"]
    current_staff = db.query(UserDB).filter(
        UserDB.school_id == user.school_id,
        UserDB.role != "Parent",
    ).count()

    if current_staff + len(valid_rows) > max_staff:
        raise HTTPException(
            status_code=403,
            detail=f"Staff limit exceeded. Adding {len(valid_rows)} faculty would exceed your limit ({current_staff + len(valid_rows)}/{max_staff}).",
        )

    import json as _json
    from models.user_db import DEFAULT_STAFF_PERMISSIONS

    inserted_count = 0
    assigned_count = 0
    created_creds = []

    try:
        for r in valid_rows:
            role = r.get("role") or "Teacher"
            if role.lower() == "admin":
                perms_final = {k: True for k in DEFAULT_STAFF_PERMISSIONS}
            else:
                perms_final = {**DEFAULT_STAFF_PERMISSIONS}

            default_pass = "Faculty@123"
            new_u = UserDB(
                school_id=user.school_id,
                email=r["email"].strip().lower(),
                password_hash=hash_password(default_pass),
                full_name=r["full_name"].strip(),
                phone=r.get("phone"),
                role=role,
                is_active=True,
                email_verified=True,
                must_reset_password=True,
                permissions_json=_json.dumps(perms_final),
            )
            db.add(new_u)
            db.flush()
            inserted_count += 1

            created_creds.append({
                "id": str(new_u.id),
                "name": new_u.full_name,
                "email": new_u.email,
                "phone": new_u.phone or "N/A",
                "role": new_u.role,
                "initial_password": default_pass,
            })

            # Optional Class and Subject Assignment
            assigned_grade = r.get("assigned_grade")
            assigned_section = r.get("assigned_section")
            subject_name = r.get("subject_name")

            if assigned_grade and assigned_section:
                sub_id = None
                if subject_name:
                    subj = db.query(Subject).filter(
                        Subject.school_id == user.school_id,
                        Subject.name.ilike(subject_name.strip())
                    ).first()
                    if not subj:
                        subj = Subject(
                            school_id=user.school_id,
                            name=subject_name.strip().title(),
                            code=subject_name.strip()[:4].upper()
                        )
                        db.add(subj)
                        db.flush()
                    sub_id = subj.id

                role_t = "ClassTeacher" if role.lower() == "classteacher" else "SubjectTeacher"
                existing_assign = db.query(TeacherAssignmentDB).filter(
                    TeacherAssignmentDB.school_id == user.school_id,
                    TeacherAssignmentDB.teacher_user_id == new_u.id,
                    TeacherAssignmentDB.grade == assigned_grade,
                    TeacherAssignmentDB.section == assigned_section,
                ).first()
                if not existing_assign:
                    assignment = TeacherAssignmentDB(
                        school_id=user.school_id,
                        teacher_user_id=new_u.id,
                        grade=assigned_grade,
                        section=assigned_section,
                        role_type=role_t,
                        subject_id=sub_id,
                    )
                    db.add(assignment)
                    assigned_count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database commit failed: {str(e)}")

    return {
        "status": "ok",
        "inserted_faculty": inserted_count,
        "assigned_classes": assigned_count,
        "credentials": created_creds,
        "message": f"Successfully enrolled {inserted_count} faculty members ({assigned_count} class leads assigned)!",
    }



# ─────────────────────────────────────────
# Exams Management CRUD
# ─────────────────────────────────────────
@router.get("/exams")
def admin_list_exams(
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    rows = db.query(Exam).filter(Exam.school_id == user.school_id).order_by(Exam.date.desc()).all()
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "term": e.term,
            "grade": e.grade,
            "date": e.date.isoformat() if e.date else None,
            "total_marks": e.total_marks,
            "exam_type": e.exam_type,
            "is_published": e.is_published,
        }
        for e in rows
    ]


@router.post("/exams")
def admin_create_exam(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    name = (payload.get("name") or "").strip()
    term = (payload.get("term") or "Term 1").strip()
    grade = (payload.get("grade") or "10").strip()
    date_str = payload.get("date")
    total_marks = float(payload.get("total_marks") or 100.0)
    exam_type = payload.get("exam_type") or "Term Exam"

    if not name or not date_str:
        raise HTTPException(status_code=400, detail="Name and Date are required")

    try:
        ex_date = date.fromisoformat(date_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")

    ex = Exam(
        school_id=user.school_id,
        name=name,
        term=term,
        grade=grade,
        date=ex_date,
        total_marks=total_marks,
        exam_type=exam_type,
        is_published=True,
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)

    return {
        "status": "ok",
        "exam": {
            "id": str(ex.id),
            "name": ex.name,
            "term": ex.term,
            "total_marks": ex.total_marks,
        },
    }


# ─────────────────────────────────────────
# Subjects Management CRUD
# ─────────────────────────────────────────
@router.get("/subjects")
def admin_list_subjects(
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    rows = db.query(Subject).filter(Subject.school_id == user.school_id).order_by(Subject.sort_order.asc(), Subject.name.asc()).all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "code": s.code,
            "sort_order": s.sort_order,
        }
        for s in rows
    ]


@router.post("/subjects")
def admin_create_subject(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "").strip() or None
    sort_order = int(payload.get("sort_order") or 0)

    if not name:
        raise HTTPException(status_code=400, detail="Subject name is required")

    sub = Subject(school_id=user.school_id, name=name, code=code, sort_order=sort_order)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"status": "ok", "subject": {"id": str(sub.id), "name": sub.name, "code": sub.code}}


# ─────────────────────────────────────────
# Teacher ↔ Class Assignments
# ─────────────────────────────────────────
@router.get("/mappings/teacher-assignments")
def admin_list_teacher_assignments(
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    rows = db.query(TeacherAssignmentDB, UserDB).join(UserDB, TeacherAssignmentDB.teacher_user_id == UserDB.id).filter(TeacherAssignmentDB.school_id == user.school_id).all()
    return [
        {
            "id": str(a.id),
            "teacher_id": str(a.teacher_user_id),
            "teacher_name": u.full_name,
            "grade": a.grade,
            "section": a.section,
            "role_type": a.role_type,
        }
        for a, u in rows
    ]


@router.post("/mappings/teacher-assignments")
def admin_assign_teacher(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    teacher_user_id = payload.get("teacher_user_id")
    grade = (payload.get("grade") or "").strip()
    section = (payload.get("section") or "").strip().upper()
    role_type = payload.get("role_type") or "ClassTeacher"

    if not teacher_user_id or not grade or not section:
        raise HTTPException(status_code=400, detail="Teacher, grade, and section are required")

    assign = TeacherAssignmentDB(
        school_id=user.school_id,
        teacher_user_id=teacher_user_id,
        grade=grade,
        section=section,
        role_type=role_type,
    )
    db.add(assign)
    db.commit()
    return {"status": "ok", "message": "Teacher assigned successfully"}




# ─────────────────────────────────────────
# Exam Update / Delete
# ─────────────────────────────────────────
@router.put("/exams/{exam_id}")
def admin_update_exam(
    exam_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Update an exam's details."""
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.school_id == user.school_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if "name" in payload and payload["name"]:
        exam.name = payload["name"].strip()
    if "term" in payload:
        exam.term = payload["term"]
    if "grade" in payload:
        exam.grade = payload["grade"]
    if "date" in payload:
        exam.date = datetime.strptime(payload["date"], "%Y-%m-%d").date()
    if "total_marks" in payload:
        exam.total_marks = int(payload["total_marks"])
    if "exam_type" in payload:
        exam.exam_type = payload["exam_type"]

    db.commit()
    return {"status": "ok", "message": f"Exam '{exam.name}' updated"}


@router.delete("/exams/{exam_id}")
def admin_delete_exam(
    exam_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Delete an exam."""
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.school_id == user.school_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    db.delete(exam)
    db.commit()
    return {"status": "ok", "message": f"Exam '{exam.name}' deleted"}


# ─────────────────────────────────────────
# Subject Update / Delete
# ─────────────────────────────────────────
@router.put("/subjects/{subject_id}")
def admin_update_subject(
    subject_id: str,
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Update a subject."""
    subj = db.query(Subject).filter(Subject.id == subject_id, Subject.school_id == user.school_id).first()
    if not subj:
        raise HTTPException(status_code=404, detail="Subject not found")

    if "name" in payload and payload["name"]:
        subj.name = payload["name"].strip()
    if "code" in payload:
        subj.code = (payload["code"] or "").strip()
    if "sort_order" in payload:
        subj.sort_order = int(payload["sort_order"])

    db.commit()
    return {"status": "ok", "message": f"Subject '{subj.name}' updated"}


@router.delete("/subjects/{subject_id}")
def admin_delete_subject(
    subject_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Delete a subject."""
    subj = db.query(Subject).filter(Subject.id == subject_id, Subject.school_id == user.school_id).first()
    if not subj:
        raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(subj)
    db.commit()
    return {"status": "ok", "message": f"Subject '{subj.name}' deleted"}


# ─────────────────────────────────────────
# Teacher Assignment Delete
# ─────────────────────────────────────────
@router.delete("/mappings/teacher-assignments/{assignment_id}")
def admin_delete_teacher_assignment(
    assignment_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Remove a teacher-class assignment."""
    assign = db.query(TeacherAssignmentDB).filter(
        TeacherAssignmentDB.id == assignment_id,
        TeacherAssignmentDB.school_id == user.school_id,
    ).first()
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assign)
    db.commit()
    return {"status": "ok", "message": "Teacher assignment removed"}
