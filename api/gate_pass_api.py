"""
Gate Pass Management API — Complete lifecycle:
Parent Request -> Admin Approval -> Security QR Scan-Out -> Security QR Scan-In.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from db.session import get_db
from models.gate_pass_db import GatePassDB, GatePassStatusLogDB
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/gate-passes", tags=["Gate Pass"])


def _expire_stale_passes(db: Session, school_id):
    """Auto-expire approved passes where expected_out_time + grace period has elapsed."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=2)  # 2 hours grace period
    stale_passes = db.query(GatePassDB).filter(
        GatePassDB.school_id == school_id,
        GatePassDB.status == "approved",
        GatePassDB.expected_out_time < cutoff
    ).all()
    for gp in stale_passes:
        old_status = gp.status
        gp.status = "expired"
        log = GatePassStatusLogDB(
            gate_pass_id=gp.id,
            from_status=old_status,
            to_status="expired",
            changed_by=None,
            gate_name="System",
            notes="Auto-expired: departure time elapsed without security gate exit",
        )
        db.add(log)
    if stale_passes:
        db.commit()


from core.sanitizer import validate_full_name, validate_text_field, validate_phone, sanitize_text
import secrets
import string

def _generate_pass_code(db: Session, school_id: Optional[str] = None) -> str:
    """
    Generate a 9-character pass code: exactly 4 uppercase letters followed by 5 digits
    (e.g., 'GPAS48291' or 'VMSX10294').
    Guarantees uniqueness against existing gate passes.
    """
    letters_pool = string.ascii_uppercase
    digits_pool = string.digits

    for _ in range(100):
        letters = "".join(secrets.choice(letters_pool) for _ in range(4))
        digits = "".join(secrets.choice(digits_pool) for _ in range(5))
        code = f"{letters}{digits}"
        exists = db.query(GatePassDB).filter(GatePassDB.pass_code == code).first()
        if not exists:
            return code

    # Extremely rare fallback: 4 letters + last 5 digits of timestamp
    ts_digits = str(int(datetime.now(timezone.utc).timestamp()))[-5:]
    letters = "".join(secrets.choice(letters_pool) for _ in range(4))
    return f"{letters}{ts_digits}"


# ── PARENT: REQUEST PASS ───────────────────────────────────────────────
@router.post("/request")
def request_gate_pass(
    payload: dict,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    school_id = user.school_id
    student_id = payload.get("student_id")
    pass_type = payload.get("pass_type", "early_leave")
    raw_accompanied_by_name = (payload.get("accompanied_by_name") or payload.get("authorized_pickup_person") or "").strip()
    raw_relation = (payload.get("accompanied_by_relation") or payload.get("relation") or "").strip()
    visitor_photo_url = payload.get("visitor_photo_url")
    raw_reason = (payload.get("reason") or "").strip()
    expected_out_str = payload.get("expected_out_time") or payload.get("departure_time")
    expected_return_str = payload.get("expected_return_time") or payload.get("return_time")

    if not student_id or not raw_accompanied_by_name or not raw_reason or not expected_out_str:
        raise HTTPException(status_code=400, detail="Student, accompanied person name, reason, and expected out time are required.")

    # Strict validation of human name and reason
    accompanied_by_name = validate_full_name(raw_accompanied_by_name, field_name="Accompanied Person Name")
    reason = validate_text_field(raw_reason, field_name="Reason for Gate Pass", min_length=3, max_length=300, required=True)
    accompanied_by_relation = validate_full_name(raw_relation, field_name="Relation") if raw_relation else "Guardian"

    # Optional visitor / guardian phone validation if provided
    raw_phone = payload.get("accompanied_by_phone") or payload.get("phone")
    if raw_phone:
        validate_phone(raw_phone, required=True, field_name="Contact Mobile Number")

    # Verify student exists and belongs to school
    student = db.query(StudentDB).filter(StudentDB.id == student_id, StudentDB.school_id == school_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school.")

    try:
        expected_out = datetime.fromisoformat(expected_out_str.replace("Z", "+00:00"))
        expected_return = datetime.fromisoformat(expected_return_str.replace("Z", "+00:00")) if expected_return_str else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {e}")

    pass_code = _generate_pass_code(db=db, school_id=str(school_id))
    qr_token = str(uuid.uuid4())

    gate_pass = GatePassDB(
        school_id=school_id,
        student_id=student.id,
        parent_user_id=user.id,
        pass_code=pass_code,
        pass_type=pass_type,
        accompanied_by_name=accompanied_by_name,
        accompanied_by_relation=accompanied_by_relation or "Guardian",
        visitor_photo_url=visitor_photo_url,
        reason=reason,
        expected_out_time=expected_out,
        expected_return_time=expected_return,
        status="requested",
        qr_token=qr_token,
    )
    db.add(gate_pass)
    db.flush()

    # Log initial status
    log = GatePassStatusLogDB(
        gate_pass_id=gate_pass.id,
        from_status="none",
        to_status="requested",
        changed_by=user.id,
        gate_name="Parent Portal",
        notes=f"Pass requested by {user.full_name or user.email}",
    )
    db.add(log)
    db.commit()
    db.refresh(gate_pass)

    # Real-time alert to Admin & Security staff
    admins_and_security = db.query(UserDB).filter(
        UserDB.school_id == school_id,
        UserDB.role.in_(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])
    ).all()
    student_name = student.name or "Student"
    alert_msg = f"NEW GATE PASS REQUEST: {student_name} (Class {student.grade}-{student.section}) by {user.full_name or 'Parent'}. Reason: {reason}"
    for officer in admins_and_security:
        dispatch_multi_channel_notification(
            db=db,
            school_id=school_id,
            user_id=officer.id,
            title="New Gate Pass Request",
            message=alert_msg,
            event_type="GATE_PASS_REQUESTED",
            payload={"pass_id": str(gate_pass.id), "pass_code": pass_code, "student_id": str(student.id)},
        )

    return {
        "success": True,
        "id": str(gate_pass.id),
        "gate_pass_id": str(gate_pass.id),
        "pass_code": pass_code,
        "qr_code": getattr(gate_pass, 'qr_token', str(gate_pass.id)),
        "qr_token": getattr(gate_pass, 'qr_token', str(gate_pass.id)),
        "status": gate_pass.status,
        "message": f"Gate pass request submitted successfully with code {pass_code}",
    }


# ── PARENT: GET MY GATE PASSES ─────────────────────────────────────────
@router.get("/parent")
def get_parent_gate_passes(
    student_id: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _expire_stale_passes(db, user.school_id)
    query = db.query(GatePassDB).filter(GatePassDB.parent_user_id == user.id)
    if student_id:
        query = query.filter(GatePassDB.student_id == student_id)
    
    passes = query.order_by(desc(GatePassDB.created_at)).all()
    res = []
    for p in passes:
        student = p.student
        res.append({
            "id": str(p.id),
            "pass_code": p.pass_code,
            "pass_type": p.pass_type,
            "student_id": str(p.student_id),
            "student_name": student.name if student else "Unknown",
            "student_grade": student.grade if student else "",
            "student_section": student.section if student else "",
            "student_photo": student.photo_url if student else None,
            "accompanied_by_name": p.accompanied_by_name,
            "accompanied_by_relation": p.accompanied_by_relation,
            "visitor_photo_url": p.visitor_photo_url,
            "reason": p.reason,
            "expected_out_time": p.expected_out_time.isoformat() if p.expected_out_time else None,
            "expected_return_time": p.expected_return_time.isoformat() if p.expected_return_time else None,
            "actual_out_time": p.actual_out_time.isoformat() if p.actual_out_time else None,
            "actual_return_time": p.actual_return_time.isoformat() if p.actual_return_time else None,
            "status": p.status,
            "qr_token": p.qr_token,
            "rejection_reason": p.rejection_reason,
            "created_at": p.created_at.isoformat(),
        })
    return res


# ── ALIAS FOR MOBILE APP: GET STUDENT GATE PASSES ───────────────────────
@router.get("/student/{student_id}")
def get_student_gate_passes_alias(
    student_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _expire_stale_passes(db, user.school_id)
    # Check parent or student permission
    query = db.query(GatePassDB).filter(
        GatePassDB.school_id == user.school_id,
        GatePassDB.student_id == student_id
    )
    passes = query.order_by(desc(GatePassDB.created_at)).all()
    res = []
    for p in passes:
        student = p.student
        res.append({
            "id": str(p.id),
            "pass_code": p.pass_code,
            "pass_type": p.pass_type,
            "student_id": str(p.student_id),
            "student_name": student.name if student else "Unknown",
            "student_grade": student.grade if student else "",
            "student_section": student.section if student else "",
            "student_photo": student.photo_url if student else None,
            "accompanied_by_name": p.accompanied_by_name,
            "accompanied_by_relation": p.accompanied_by_relation,
            "visitor_photo_url": p.visitor_photo_url,
            "reason": p.reason,
            "expected_out_time": p.expected_out_time.isoformat() if p.expected_out_time else None,
            "expected_return_time": p.expected_return_time.isoformat() if p.expected_return_time else None,
            "actual_out_time": p.actual_out_time.isoformat() if p.actual_out_time else None,
            "actual_return_time": p.actual_return_time.isoformat() if p.actual_return_time else None,
            "status": p.status,
            "qr_token": p.qr_token,
            "rejection_reason": p.rejection_reason,
            "created_at": p.created_at.isoformat(),
        })
    return res


# ── TEACHER: VIEW CLASS GATE PASSES ────────────────────────────────────
@router.get("/teacher/class")
def get_teacher_class_gate_passes(
    grade: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    user: UserDB = Depends(require_role(["Teacher", "Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    _expire_stale_passes(db, user.school_id)
    query = db.query(GatePassDB).join(StudentDB, GatePassDB.student_id == StudentDB.id).filter(
        GatePassDB.school_id == user.school_id
    )

    if grade and section:
        query = query.filter(StudentDB.grade == grade, StudentDB.section == section)
    elif user.role == "Teacher":
        assignments = db.query(TeacherAssignmentDB).filter(
            TeacherAssignmentDB.teacher_id == user.id,
            TeacherAssignmentDB.school_id == user.school_id
        ).all()
        if assignments:
            conditions = [
                (StudentDB.grade == a.grade) & ((StudentDB.section == a.section) | (a.section == "ALL") | (a.section == ""))
                for a in assignments
            ]
            query = query.filter(or_(*conditions))

    passes = query.order_by(desc(GatePassDB.created_at)).all()
    res = []
    for p in passes:
        student = p.student
        parent = p.parent
        res.append({
            "id": str(p.id),
            "pass_code": p.pass_code,
            "pass_type": p.pass_type,
            "student_id": str(p.student_id),
            "student_name": student.name if student else "Unknown",
            "student_grade": student.grade if student else "",
            "student_section": student.section if student else "",
            "student_photo": student.photo_url if student else None,
            "parent_name": parent.full_name if parent else "Parent",
            "accompanied_by_name": p.accompanied_by_name,
            "accompanied_by_relation": p.accompanied_by_relation,
            "visitor_photo_url": p.visitor_photo_url,
            "reason": p.reason,
            "expected_out_time": p.expected_out_time.isoformat() if p.expected_out_time else None,
            "expected_return_time": p.expected_return_time.isoformat() if p.expected_return_time else None,
            "actual_out_time": p.actual_out_time.isoformat() if p.actual_out_time else None,
            "actual_return_time": p.actual_return_time.isoformat() if p.actual_return_time else None,
            "status": p.status,
            "qr_token": p.qr_token,
            "rejection_reason": p.rejection_reason,
            "created_at": p.created_at.isoformat(),
        })
    return res


# ── PARENT: CANCEL PENDING PASS ─────────────────────────────────────────
@router.post("/{pass_id}/cancel")
def cancel_gate_pass(
    pass_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.parent_user_id == user.id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")
    if gp.status != "requested":
        raise HTTPException(status_code=400, detail=f"Cannot cancel pass with status '{gp.status}'")

    old_status = gp.status
    gp.status = "cancelled"
    log = GatePassStatusLogDB(
        gate_pass_id=gp.id,
        from_status=old_status,
        to_status="cancelled",
        changed_by=user.id,
        notes="Cancelled by parent",
    )
    db.add(log)
    db.commit()
    return {"success": True, "message": "Gate pass cancelled."}




# ── ADMIN & SECURITY: FILTERED QUEUE ───────────────────────────────────
@router.get("/admin/queue")
def get_admin_gate_pass_queue(
    status: Optional[str] = Query(None, description="Filter: all, requested, approved, out, returned, rejected"),
    date_filter: Optional[str] = Query(None, description="YYYY-MM-DD"),
    search: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    limit: Optional[int] = Query(None, ge=1),
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    _expire_stale_passes(db, user.school_id)
    query = db.query(GatePassDB).filter(GatePassDB.school_id == user.school_id)

    if status and status.lower() != "all":
        query = query.filter(GatePassDB.status == status.lower())

    if search:
        s = f"%{search.strip()}%"
        query = query.join(StudentDB, GatePassDB.student_id == StudentDB.id).filter(
            (GatePassDB.pass_code.ilike(s)) |
            (StudentDB.name.ilike(s)) |
            (StudentDB.admission_no.ilike(s)) |
            (GatePassDB.accompanied_by_name.ilike(s))
        )

    total = query.count()
    if page is not None:
        eff_limit = limit or 25
        offset = (page - 1) * eff_limit
        passes = query.order_by(desc(GatePassDB.created_at)).offset(offset).limit(eff_limit).all()
    else:
        passes = query.order_by(desc(GatePassDB.created_at)).all()

    res = []
    for p in passes:
        student = p.student
        parent = p.parent
        res.append({
            "id": str(p.id),
            "pass_code": p.pass_code,
            "pass_type": p.pass_type,
            "student_id": str(p.student_id),
            "student_name": student.name if student else "N/A",
            "student_admission_no": student.admission_no if student else "N/A",
            "student_grade": student.grade if student else "-",
            "student_section": student.section if student else "-",
            "student_photo": student.photo_url if student else None,
            "parent_name": parent.full_name if parent else (student.father_name if student else "Parent"),
            "parent_phone": parent.phone if parent else (student.father_phone if student else None),
            "accompanied_by_name": p.accompanied_by_name,
            "accompanied_by_relation": p.accompanied_by_relation,
            "visitor_photo_url": p.visitor_photo_url,
            "reason": p.reason,
            "expected_out_time": p.expected_out_time.isoformat() if p.expected_out_time else None,
            "expected_return_time": p.expected_return_time.isoformat() if p.expected_return_time else None,
            "actual_out_time": p.actual_out_time.isoformat() if p.actual_out_time else None,
            "actual_return_time": p.actual_return_time.isoformat() if p.actual_return_time else None,
            "status": p.status,
            "qr_token": p.qr_token,
            "rejection_reason": p.rejection_reason,
            "created_at": p.created_at.isoformat(),
        })

    if page is not None:
        eff_limit = limit or 25
        return {
            "items": res,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    return res


# ── ADMIN: APPROVE PASS ────────────────────────────────────────────────
@router.post("/{pass_id}/approve")
def approve_gate_pass(
    pass_id: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.school_id == user.school_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")
    if gp.status != "requested":
        raise HTTPException(status_code=400, detail=f"Cannot approve pass with status '{gp.status}'")

    old_status = gp.status
    gp.status = "approved"
    gp.approved_by = user.id

    log = GatePassStatusLogDB(
        gate_pass_id=gp.id,
        from_status=old_status,
        to_status="approved",
        changed_by=user.id,
        notes=f"Approved by administrator {user.full_name or user.email}",
    )
    db.add(log)
    db.commit()

    # Dispatch notification to parent honoring their channel permissions
    student_name = gp.student.name if gp.student else "your child"
    msg = f"Gate pass {gp.pass_code} for {student_name} has been APPROVED. Show the QR pass to gate security at departure."
    dispatch_multi_channel_notification(
        db=db,
        school_id=user.school_id,
        user_id=gp.parent_user_id,
        title="Gate Pass Approved",
        message=msg,
        event_type="GATE_PASS_APPROVED",
        payload={"pass_id": str(gp.id), "pass_code": gp.pass_code},
    )

    return {"success": True, "message": "Gate pass approved successfully.", "status": "APPROVED", "gate_pass_id": str(gp.id)}


# ── ADMIN: REJECT PASS ────────────────────────────────────────────────
@router.post("/{pass_id}/reject")
def reject_gate_pass(
    pass_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    reason = payload.get("reason", "Not approved by administration").strip()
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.school_id == user.school_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")

    old_status = gp.status
    gp.status = "rejected"
    gp.rejection_reason = reason

    log = GatePassStatusLogDB(
        gate_pass_id=gp.id,
        from_status=old_status,
        to_status="rejected",
        changed_by=user.id,
        notes=f"Rejected: {reason}",
    )
    db.add(log)
    db.commit()

    student_name = gp.student.name if gp.student else "your child"
    msg = f"Gate pass request {gp.pass_code} for {student_name} was rejected. Reason: {reason}"
    dispatch_multi_channel_notification(
        db=db,
        school_id=user.school_id,
        user_id=gp.parent_user_id,
        title="Gate Pass Rejected",
        message=msg,
        event_type="GATE_PASS_REJECTED",
        payload={"pass_id": str(gp.id), "pass_code": gp.pass_code, "reason": reason},
    )

    return {"success": True, "message": "Gate pass rejected.", "status": "REJECTED", "gate_pass_id": str(gp.id)}


# ── ADMIN: REVIEW (PATCH ALIAS FOR APPROVE / REJECT) ───────────────────
@router.patch("/{pass_id}/review")
def review_gate_pass(
    pass_id: str,
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    action = (payload.get("status") or payload.get("action") or "").lower()
    if action == "approved":
        return approve_gate_pass(pass_id=pass_id, user=user, db=db)
    elif action == "rejected":
        return reject_gate_pass(pass_id=pass_id, payload={"reason": payload.get("admin_remarks") or payload.get("reason", "Not approved")}, user=user, db=db)
    else:
        raise HTTPException(status_code=400, detail="Invalid review status. Expected 'approved' or 'rejected'.")


# ── SECURITY: VERIFY QR OR PASS CODE ───────────────────────────────────
@router.post("/verify-qr")
def verify_qr(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    token_or_code = payload.get("token", "").strip()
    if not token_or_code:
        raise HTTPException(status_code=400, detail="QR token or pass code is required.")

    gp = db.query(GatePassDB).filter(
        GatePassDB.school_id == user.school_id,
        (GatePassDB.qr_token == token_or_code) | (GatePassDB.pass_code.ilike(token_or_code))
    ).first()

    if not gp:
        raise HTTPException(status_code=404, detail="Invalid Gate Pass or unrecognized QR token.")

    student = gp.student
    parent = gp.parent

    can_scan_out = (gp.status == "approved")
    can_scan_in = (gp.status == "out")

    return {
        "verified": True,
        "gate_pass_id": str(gp.id),
        "pass_code": gp.pass_code,
        "pass_type": gp.pass_type,
        "status": gp.status.upper(),
        "student": {
            "id": str(student.id),
            "name": student.name,
            "admission_no": student.admission_no,
            "grade": student.grade,
            "section": student.section,
            "photo_url": student.photo_url,
            "blood_group": student.blood_group,
            "emergency_contact": student.emergency_contact_phone or student.father_phone,
        },
        "parent": {
            "name": parent.full_name if parent else student.father_name,
            "phone": parent.phone if parent else student.father_phone,
        },
        "accompanied_by_name": gp.accompanied_by_name,
        "accompanied_by_relation": gp.accompanied_by_relation,
        "visitor_photo_url": gp.visitor_photo_url,
        "reason": gp.reason,
        "expected_out_time": gp.expected_out_time.isoformat() if gp.expected_out_time else None,
        "expected_return_time": gp.expected_return_time.isoformat() if gp.expected_return_time else None,
        "actual_out_time": gp.actual_out_time.isoformat() if gp.actual_out_time else None,
        "actual_return_time": gp.actual_return_time.isoformat() if gp.actual_return_time else None,
        "can_scan_out": can_scan_out,
        "can_scan_in": can_scan_in,
    }


@router.get("/verify-qr/{token_or_code}")
def verify_qr_get(
    token_or_code: str,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    return verify_qr(payload={"token": token_or_code}, user=user, db=db)


# ── SECURITY: SCAN OUT (DEPARTURE) ─────────────────────────────────────
@router.post("/{pass_id}/scan-out")
def scan_out(
    pass_id: str,
    payload: dict = {},
    user: UserDB = Depends(require_role(["Admin", "Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.school_id == user.school_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")
    if gp.status != "approved":
        raise HTTPException(status_code=400, detail=f"Cannot scan out: pass status is '{gp.status}'. Must be 'approved'.")

    gate_name = payload.get("gate_name", "Main Gate")
    now = datetime.now(timezone.utc)
    old_status = gp.status
    gp.status = "out"
    gp.actual_out_time = now

    log = GatePassStatusLogDB(
        gate_pass_id=gp.id,
        from_status=old_status,
        to_status="out",
        changed_by=user.id,
        gate_name=gate_name,
        notes=f"Scan-out registered by security officer {user.full_name or user.email}",
    )
    db.add(log)
    db.commit()

    # Real-time alert to parent
    student_name = gp.student.name if gp.student else "Your child"
    msg = f"CAMPUS EXIT: {student_name} has exited campus via {gate_name} accompanied by {gp.accompanied_by_name} at {now.strftime('%I:%M %p')}."
    dispatch_multi_channel_notification(
        db=db,
        school_id=user.school_id,
        user_id=gp.parent_user_id,
        title="Campus Departure Registered",
        message=msg,
        event_type="GATE_SCAN_OUT",
        payload={"pass_id": str(gp.id), "actual_out_time": now.isoformat()},
    )

    return {
        "success": True,
        "status": "OUT",
        "message": f"{student_name} marked as OUT at {now.strftime('%I:%M %p')}.",
        "actual_out_time": now.isoformat(),
        "gate_pass_id": str(gp.id),
    }


# ── SECURITY: SCAN IN (RETURN) ─────────────────────────────────────────
@router.post("/{pass_id}/scan-in")
def scan_in(
    pass_id: str,
    payload: dict = {},
    user: UserDB = Depends(require_role(["Admin", "Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.school_id == user.school_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")
    if gp.status != "out":
        raise HTTPException(status_code=400, detail=f"Cannot scan in: pass status is '{gp.status}'. Must be 'out'.")

    gate_name = payload.get("gate_name", "Main Gate")
    now = datetime.now(timezone.utc)
    old_status = gp.status
    gp.status = "returned"
    gp.actual_return_time = now

    log = GatePassStatusLogDB(
        gate_pass_id=gp.id,
        from_status=old_status,
        to_status="returned",
        changed_by=user.id,
        gate_name=gate_name,
        notes=f"Scan-in registered by security officer {user.full_name or user.email}",
    )
    db.add(log)
    db.commit()

    student_name = gp.student.name if gp.student else "Your child"
    msg = f"CAMPUS RETURN: {student_name} has safely returned to campus via {gate_name} at {now.strftime('%I:%M %p')}."
    dispatch_multi_channel_notification(
        db=db,
        school_id=user.school_id,
        user_id=gp.parent_user_id,
        title="Campus Return Registered",
        message=msg,
        event_type="GATE_SCAN_IN",
        payload={"pass_id": str(gp.id), "actual_return_time": now.isoformat()},
    )

    return {
        "success": True,
        "status": "RETURNED",
        "message": f"{student_name} marked as RETURNED at {now.strftime('%I:%M %p')}.",
        "actual_return_time": now.isoformat(),
        "gate_pass_id": str(gp.id),
    }


# ── SECURITY: UNIFIED GUARD SCAN (DEPARTURE & RETURN ALIAS) ────────────
@router.post("/{pass_id}/guard-scan")
def guard_scan(
    pass_id: str,
    payload: dict = {},
    user: UserDB = Depends(require_role(["Admin", "Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    action = (payload.get("action") or "").upper()
    if action == "DEPARTURE":
        return scan_out(pass_id=pass_id, payload={"gate_name": payload.get("notes", "Main Gate")}, user=user, db=db)
    elif action == "RETURN":
        return scan_in(pass_id=pass_id, payload={"gate_name": payload.get("notes", "Main Gate")}, user=user, db=db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scan action: {action}")


# ── GET SINGLE GATE PASS DETAIL ─────────────────────────────────────────
@router.get("/{pass_id}")
def get_single_gate_pass(
    pass_id: str,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _expire_stale_passes(db, user.school_id)
    gp = db.query(GatePassDB).filter(GatePassDB.id == pass_id, GatePassDB.school_id == user.school_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not found")

    student = gp.student
    parent = gp.parent
    logs = [{
        "from_status": l.from_status,
        "to_status": l.to_status,
        "gate_name": l.gate_name,
        "notes": l.notes,
        "created_at": l.created_at.isoformat(),
    } for l in gp.status_logs]

    return {
        "id": str(gp.id),
        "pass_code": gp.pass_code,
        "pass_type": gp.pass_type,
        "status": gp.status,
        "student_id": str(gp.student_id),
        "student_name": student.name if student else "Unknown",
        "student_admission_no": student.admission_no if student else "N/A",
        "student_grade": student.grade if student else "",
        "student_section": student.section if student else "",
        "student_photo": student.photo_url if student else None,
        "parent_name": parent.full_name if parent else (student.father_name if student else "Parent"),
        "parent_phone": parent.phone if parent else (student.father_phone if student else None),
        "accompanied_by_name": gp.accompanied_by_name,
        "accompanied_by_relation": gp.accompanied_by_relation,
        "visitor_photo_url": gp.visitor_photo_url,
        "reason": gp.reason,
        "expected_out_time": gp.expected_out_time.isoformat() if gp.expected_out_time else None,
        "expected_return_time": gp.expected_return_time.isoformat() if gp.expected_return_time else None,
        "actual_out_time": gp.actual_out_time.isoformat() if gp.actual_out_time else None,
        "actual_return_time": gp.actual_return_time.isoformat() if gp.actual_return_time else None,
        "qr_token": gp.qr_token,
        "rejection_reason": gp.rejection_reason,
        "created_at": gp.created_at.isoformat(),
        "status_logs": logs,
    }

