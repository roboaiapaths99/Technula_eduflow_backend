"""
Visitor Log API — Front-Desk Walk-Ins, Campus Visitors, and Filtered Audit Views.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from db.session import get_db
from models.visitor_log_db import VisitorLogDB
from models.student_db import StudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/visitors", tags=["Visitor Logs"])


@router.post("/")
@router.post("/check-in")
def log_visitor_entry(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    visitor_name = payload.get("visitor_name", "").strip()
    visitor_phone = payload.get("visitor_phone", "").strip()
    purpose = payload.get("purpose", "guest_meeting")
    person_to_meet = payload.get("person_to_meet", "").strip()
    id_proof_type = payload.get("id_proof_type")
    id_proof_number = payload.get("id_proof_number")
    visitor_photo_url = payload.get("visitor_photo_url")
    student_id = payload.get("student_id")
    gate_pass_id = payload.get("gate_pass_id")
    gate_name = payload.get("gate_name", "Main Gate")
    notes = payload.get("notes")

    if not visitor_name or not visitor_phone:
        raise HTTPException(status_code=400, detail="Visitor name and phone number are required.")

    log = VisitorLogDB(
        school_id=user.school_id,
        visitor_name=visitor_name,
        visitor_phone=visitor_phone,
        visitor_photo_url=visitor_photo_url,
        purpose=purpose,
        student_id=student_id,
        gate_pass_id=gate_pass_id,
        person_to_meet=person_to_meet,
        id_proof_type=id_proof_type,
        id_proof_number=id_proof_number,
        gate_name=gate_name,
        logged_by_user_id=user.id,
        notes=notes,
        status="checked_in",
        check_in_time=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "success": True,
        "message": f"Visitor {visitor_name} checked in successfully at {gate_name}.",
        "id": str(log.id),
        "visitor_id": str(log.id),
        "badge_number": f"VIS-{str(log.id)[:6].upper()}",
        "check_in_time": log.check_in_time.isoformat(),
    }


@router.get("/")
def get_visitor_logs(
    status: Optional[str] = Query(None, description="all, checked_in, checked_out"),
    date_filter: Optional[str] = Query(None, description="YYYY-MM-DD"),
    search: Optional[str] = Query(None),
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    query = db.query(VisitorLogDB).filter(VisitorLogDB.school_id == user.school_id)

    if status and status.lower() != "all":
        query = query.filter(VisitorLogDB.status == status.lower())

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (VisitorLogDB.visitor_name.ilike(s)) |
            (VisitorLogDB.visitor_phone.ilike(s)) |
            (VisitorLogDB.person_to_meet.ilike(s))
        )

    logs = query.order_by(desc(VisitorLogDB.check_in_time)).all()

    res = []
    for l in logs:
        student = l.student
        res.append({
            "id": str(l.id),
            "visitor_name": l.visitor_name,
            "visitor_phone": l.visitor_phone,
            "visitor_photo_url": l.visitor_photo_url,
            "purpose": l.purpose,
            "person_to_meet": l.person_to_meet,
            "id_proof_type": l.id_proof_type,
            "id_proof_number": l.id_proof_number,
            "gate_name": l.gate_name,
            "student_id": str(l.student_id) if l.student_id else None,
            "student_name": student.name if student else None,
            "student_grade": f"{student.grade}-{student.section}" if student else None,
            "gate_pass_id": str(l.gate_pass_id) if l.gate_pass_id else None,
            "check_in_time": l.check_in_time.isoformat() if l.check_in_time else None,
            "check_out_time": l.check_out_time.isoformat() if l.check_out_time else None,
            "status": l.status,
            "notes": l.notes,
        })
    return res


@router.post("/{visitor_id}/checkout")
@router.patch("/{visitor_id}/check-out")
def checkout_visitor(
    visitor_id: str,
    guard_user_id: Optional[str] = Query(None),
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    log = db.query(VisitorLogDB).filter(VisitorLogDB.id == visitor_id, VisitorLogDB.school_id == user.school_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Visitor log entry not found")
    if log.status == "checked_out":
        return {
            "success": True,
            "message": "Visitor is already checked out.",
            "status": "CHECKED_OUT",
            "check_out_time": log.check_out_time.isoformat() if log.check_out_time else datetime.now(timezone.utc).isoformat(),
        }

    now = datetime.now(timezone.utc)
    log.status = "checked_out"
    log.check_out_time = now
    db.commit()

    return {
        "success": True,
        "message": f"Visitor {log.visitor_name} checked out at {now.strftime('%I:%M %p')}.",
        "status": "CHECKED_OUT",
        "check_out_time": now.isoformat(),
    }


@router.get("/stats")
def get_visitor_stats(
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff", "Security", "GateStaff"])),
    db: Session = Depends(get_db),
):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_today = db.query(func.count(VisitorLogDB.id)).filter(
        VisitorLogDB.school_id == user.school_id,
        VisitorLogDB.check_in_time >= today_start
    ).scalar() or 0

    active_now = db.query(func.count(VisitorLogDB.id)).filter(
        VisitorLogDB.school_id == user.school_id,
        VisitorLogDB.status == "checked_in"
    ).scalar() or 0

    checked_out_today = db.query(func.count(VisitorLogDB.id)).filter(
        VisitorLogDB.school_id == user.school_id,
        VisitorLogDB.status == "checked_out",
        VisitorLogDB.check_out_time >= today_start
    ).scalar() or 0

    return {
        "total_visitors_today": total_today,
        "currently_on_campus": active_now,
        "checked_out_today": checked_out_today,
    }
