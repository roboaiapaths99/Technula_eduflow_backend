"""
Parent Link Code API — Secure parent-student linking via unique verification codes.
Flow:
1. Admin adds student → system auto-generates a unique Parent Link Code (e.g., STU-A3X7K9)
2. Admin shares the code with the parent (SMS, printout, etc.)
3. Parent registers → enters the code → auto-verified
4. Parent registers WITHOUT code → flagged as suspicious → admin must approve
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.parent_link_code_db import ParentLinkCodeDB, _generate_link_code
from models.student_db import StudentDB
from models.user_db import UserDB
from models.parent_student_db import ParentStudentDB
from auth.dependencies import require_role, get_current_user

router = APIRouter(prefix="/parent-codes", tags=["Parent Link Codes"])


class GenerateCodeRequest(BaseModel):
    student_id: str
    relation: Optional[str] = "Guardian"  # Father, Mother, Guardian


class VerifyCodeRequest(BaseModel):
    code: str
    parent_user_id: str


# ── Admin generates codes ────────────────────────────
@router.post("/generate")
def generate_parent_code(
    req: GenerateCodeRequest,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Admin generates a unique link code for a student's parent."""
    school_id = str(user.school_id)

    # Verify student belongs to this school
    student = db.query(StudentDB).filter(
        StudentDB.id == req.student_id,
        StudentDB.school_id == school_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    code = ParentLinkCodeDB(
        school_id=school_id,
        student_id=req.student_id,
        relation=req.relation or "Guardian",
        code=_generate_link_code(),
    )
    db.add(code)
    db.commit()
    db.refresh(code)

    return {
        "status": "ok",
        "code": code.code,
        "student_name": student.name,
        "student_grade": f"{student.grade}-{student.section}",
        "message": f"Parent link code generated: {code.code}. Share this with the parent.",
    }


# ── Bulk generate codes for all students ─────────────
@router.post("/generate-bulk")
@router.post("/generate-class")
def generate_bulk_codes(
    payload: dict,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Generate link codes for all students in a grade/section who don't have one yet."""
    school_id = str(user.school_id)
    grade = payload.get("grade")
    section = payload.get("section")

    students = db.query(StudentDB).filter(
        StudentDB.school_id == school_id,
        StudentDB.grade == grade,
        StudentDB.section == section,
        StudentDB.is_active == True,
    ).all()

    generated = []
    for student in students:
        # Check if code already exists and is unused
        existing = db.query(ParentLinkCodeDB).filter(
            ParentLinkCodeDB.student_id == student.id,
            ParentLinkCodeDB.is_used == False,
        ).first()
        if existing:
            generated.append({
                "student_name": student.name,
                "admission_no": student.admission_no,
                "code": existing.code,
                "status": "existing",
            })
            continue

        code = ParentLinkCodeDB(
            school_id=school_id,
            student_id=student.id,
            code=_generate_link_code(),
        )
        db.add(code)
        generated.append({
            "student_name": student.name,
            "admission_no": student.admission_no,
            "code": code.code,
            "status": "new",
        })

    db.commit()

    return {
        "status": "ok",
        "total": len(generated),
        "codes": generated,
    }


# ── Student parent codes ─────────────────────────────
@router.get("/student/{student_id}")
def get_student_parent_codes(
    student_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Retrieve parent link codes generated for a specific student."""
    school_id = str(user.school_id)
    codes = db.query(ParentLinkCodeDB).filter(
        ParentLinkCodeDB.school_id == school_id,
        ParentLinkCodeDB.student_id == student_id,
    ).all()
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "relation": c.relation,
            "is_used": c.is_used,
            "used_at": c.used_at.isoformat() if c.used_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in codes
    ]


# ── List codes for a class ──────────────────────────
@router.get("/list")
def list_parent_codes(
    grade: Optional[str] = None,
    section: Optional[str] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """List all parent link codes for admin review."""
    school_id = str(user.school_id)

    query = db.query(ParentLinkCodeDB, StudentDB).join(
        StudentDB, ParentLinkCodeDB.student_id == StudentDB.id
    ).filter(ParentLinkCodeDB.school_id == school_id)

    if grade:
        query = query.filter(StudentDB.grade == grade)
    if section:
        query = query.filter(StudentDB.section == section)

    codes = query.order_by(StudentDB.grade.asc(), StudentDB.section.asc(), StudentDB.name.asc()).all()

    return [
        {
            "id": str(c.id),
            "code": c.code,
            "student_id": str(c.student_id),
            "student_name": s.name,
            "admission_no": s.admission_no,
            "grade": s.grade,
            "section": s.section,
            "relation": c.relation,
            "is_used": c.is_used,
            "used_at": c.used_at.isoformat() if c.used_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c, s in codes
    ]


# ── Verify code (used during parent registration) ───
@router.post("/verify")
def verify_parent_code(
    req: VerifyCodeRequest,
    db: Session = Depends(get_db),
):
    """
    Public endpoint (used during parent registration).
    Verifies the parent link code and creates the parent-student link.
    """
    code_record = db.query(ParentLinkCodeDB).filter(
        ParentLinkCodeDB.code == req.code.strip().upper(),
    ).first()

    if not code_record:
        return {
            "verified": False,
            "suspicious": True,
            "message": "Invalid code. Please contact the school admin for your parent link code.",
        }

    if code_record.is_used:
        return {
            "verified": False,
            "suspicious": True,
            "message": "This code has already been used. Contact school admin if you need a new one.",
        }

    # Mark code as used
    code_record.is_used = True
    code_record.used_by_user_id = req.parent_user_id
    code_record.used_at = datetime.now(timezone.utc)

    # Create parent-student link
    link = ParentStudentDB(
        parent_user_id=req.parent_user_id,
        student_id=code_record.student_id,
        relation=code_record.relation,
        is_primary=True,
        is_verified=True,  # Auto-verified because they had the code
    )
    db.add(link)
    db.commit()

    # Get student info for response
    student = db.query(StudentDB).filter(StudentDB.id == code_record.student_id).first()

    return {
        "verified": True,
        "suspicious": False,
        "student": {
            "id": str(student.id),
            "name": student.name,
            "grade": student.grade,
            "section": student.section,
            "admission_no": student.admission_no,
        } if student else None,
        "message": "Successfully linked to student! You can now view their data.",
    }


# ── Search & Link Child by Admission Number (Parent App) ─────
class SearchAndLinkRequest(BaseModel):
    admission_no: str
    school_id: Optional[str] = None
    link_code: Optional[str] = None
    relation: Optional[str] = "Guardian"


@router.post("/search-and-link")
def search_and_link_child(
    req: SearchAndLinkRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Secure parent child-linking by admission number.
    - If valid link_code provided -> Instant verified link
    - If parent phone matches student records -> Instant verified link
    - Otherwise -> Flagged as pending/suspicious, requiring admin confirmation
    """
    adm_no = req.admission_no.strip()
    if not adm_no:
        raise HTTPException(status_code=400, detail="Admission number is required")

    # Look up student
    query = db.query(StudentDB).filter(
        StudentDB.admission_no == adm_no,
        StudentDB.is_active == True,
    )
    if req.school_id:
        query = query.filter(StudentDB.school_id == req.school_id)

    student = query.first()
    if not student:
        raise HTTPException(
            status_code=404,
            detail="No student found matching this admission number. Please verify the number or contact your school.",
        )

    # Check if already linked
    existing_link = db.query(ParentStudentDB).filter(
        ParentStudentDB.parent_user_id == user.id,
        ParentStudentDB.student_id == student.id,
    ).first()

    if existing_link and existing_link.is_verified:
        return {
            "success": True,
            "already_linked": True,
            "verified": True,
            "student": {
                "id": str(student.id),
                "name": student.name,
                "grade": student.grade,
                "section": student.section,
                "admission_no": student.admission_no,
            },
            "message": "This student is already linked to your parent account.",
        }

    # Security Check: Validate link code or phone match
    code_valid = False
    if req.link_code and req.link_code.strip():
        code_record = db.query(ParentLinkCodeDB).filter(
            ParentLinkCodeDB.student_id == student.id,
            ParentLinkCodeDB.code == req.link_code.strip().upper(),
            ParentLinkCodeDB.is_used == False,
        ).first()
        if code_record:
            code_valid = True
            code_record.is_used = True
            code_record.used_by_user_id = user.id
            code_record.used_at = datetime.now(timezone.utc)

    # Secondary check: Phone number match
    phone_match = False
    if user.phone:
        clean_user_phone = "".join(filter(str.isdigit, user.phone))
        father_p = "".join(filter(str.isdigit, student.father_phone or ""))
        mother_p = "".join(filter(str.isdigit, student.mother_phone or ""))
        emg_p = "".join(filter(str.isdigit, student.emergency_contact_phone or ""))
        if clean_user_phone and (clean_user_phone == father_p or clean_user_phone == mother_p or clean_user_phone == emg_p):
            phone_match = True

    is_verified = code_valid or phone_match
    is_suspicious = not is_verified

    if not existing_link:
        link = ParentStudentDB(
            parent_user_id=user.id,
            student_id=student.id,
            relation=req.relation or "Guardian",
            is_primary=True,
            is_verified=is_verified,
        )
        db.add(link)
    else:
        existing_link.is_verified = is_verified
        link = existing_link

    db.commit()

    if is_verified:
        return {
            "success": True,
            "verified": True,
            "pending_approval": False,
            "student": {
                "id": str(student.id),
                "name": student.name,
                "grade": student.grade,
                "section": student.section,
                "admission_no": student.admission_no,
            },
            "message": "Student successfully linked and verified! You can now view their attendance, marks, and announcements.",
        }
    else:
        return {
            "success": True,
            "verified": False,
            "pending_approval": True,
            "student": {
                "id": str(student.id),
                "name": f"{student.name[:2]}*** (Class {student.grade}-{student.section})",
                "grade": student.grade,
                "section": student.section,
                "admission_no": student.admission_no,
            },
            "message": "Link request submitted! Because no link code was provided, your school admin must approve this link for security before full student details are shown.",
        }


# ── Pending Link Requests Queue (For School Admin) ──
@router.get("/requests/pending")
def get_pending_link_requests(
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Returns unverified parent-student link requests strictly scoped to the admin's school.
    """
    school_id = str(user.school_id) if getattr(user, "school_id", None) else None

    query = (
        db.query(ParentStudentDB, StudentDB, UserDB)
        .join(StudentDB, ParentStudentDB.student_id == StudentDB.id)
        .join(UserDB, ParentStudentDB.parent_user_id == UserDB.id)
        .filter(ParentStudentDB.is_verified == False)
    )

    if school_id:
        query = query.filter(StudentDB.school_id == school_id)

    results = query.order_by(ParentStudentDB.created_at.desc()).all()

    return [
        {
            "id": str(link.id),
            "parent_id": str(parent.id),
            "parent_name": parent.full_name or parent.email,
            "parent_email": parent.email,
            "parent_phone": parent.phone or "Not Provided",
            "student_id": str(student.id),
            "student_name": student.name,
            "admission_no": student.admission_no,
            "grade": student.grade,
            "section": student.section,
            "school_id": str(student.school_id),
            "relation": link.relation,
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
        for link, student, parent in results
    ]


@router.post("/requests/{link_id}/approve")
def approve_parent_link(
    link_id: str,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Approve an unverified parent-student link. Scoped to the admin's school.
    Dispatches in-app notification so Parent App updates in real-time.
    """
    link = db.query(ParentStudentDB).filter(ParentStudentDB.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link request not found")

    student = db.query(StudentDB).filter(StudentDB.id == link.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Associated student not found")

    if getattr(user, "school_id", None) and str(student.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Forbidden: Cannot approve link for another school's student")

    link.is_verified = True
    db.commit()

    # Dispatch notification to parent so mobile app syncs immediately
    try:
        from services.notification_service import NotificationService
        NotificationService.send_in_app(
            user_id=link.parent_user_id,
            title="Student Profile Linked! 🎓",
            message=f"School Admin approved linking for {student.name} (Class {student.grade}-{student.section}, Adm: {student.admission_no}). The profile is now active in your app!",
            event_type="STUDENT_LINK_APPROVED",
            metadata={"student_id": str(student.id), "admission_no": student.admission_no, "student_name": student.name}
        )
    except Exception as notif_err:
        pass

    return {
        "status": "ok",
        "message": f"Parent verified and linked to {student.name} ({student.admission_no})",
    }


@router.post("/requests/{link_id}/reject")
def reject_parent_link(
    link_id: str,
    payload: Optional[dict] = None,
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """
    Reject and remove an unverified parent-student link request.
    """
    link = db.query(ParentStudentDB).filter(ParentStudentDB.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link request not found")

    student = db.query(StudentDB).filter(StudentDB.id == link.student_id).first()
    if student and getattr(user, "school_id", None) and str(student.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Forbidden: Cannot reject link for another school's student")

    parent_user_id = link.parent_user_id
    student_name = student.name if student else "Student"
    reason = (payload or {}).get("reason", "Identity could not be verified by school admin.")

    db.delete(link)
    db.commit()

    try:
        from services.notification_service import NotificationService
        NotificationService.send_in_app(
            user_id=parent_user_id,
            title="Student Link Request Declined ❌",
            message=f"Link request for {student_name} was declined by the school administration. Reason: {reason}",
            event_type="STUDENT_LINK_REJECTED",
            metadata={"student_name": student_name}
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "Parent link request was rejected and removed",
    }


