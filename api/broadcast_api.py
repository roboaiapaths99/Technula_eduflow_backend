"""
Broadcast Dispatch API — Multi-channel mass announcements with strict channel permission enforcement.
"""
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/broadcast", tags=["Broadcast Communication"])


@router.post("/send")
def send_broadcast(
    payload: dict,
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Teacher", "Staff"])),
    db: Session = Depends(get_db),
):
    title = payload.get("title", "").strip()
    message = payload.get("message", "").strip()
    target_audience = payload.get("target_audience", "ALL_PARENTS")  # ALL_PARENTS, GRADE, SECTION
    grade = payload.get("grade")
    section = payload.get("section")
    channels = payload.get("channels", ["in_app", "whatsapp", "email"])

    if not title or not message:
        raise HTTPException(status_code=400, detail="Title and message are required.")

    query = db.query(StudentDB).filter(
        StudentDB.school_id == user.school_id,
        StudentDB.is_active == True,
    )

    if target_audience in ["GRADE", "SECTION"] and grade:
        query = query.filter(StudentDB.grade == str(grade))
    if target_audience == "SECTION" and section:
        query = query.filter(StudentDB.section == str(section).upper())

    students = query.all()

    sent_count = 0
    wa_sent = 0
    wa_opted_out = 0
    email_sent = 0
    email_opted_out = 0

    seen_parents = set()

    for s in students:
        links = db.query(ParentStudentDB).filter(ParentStudentDB.student_id == s.id).all()
        for link in links:
            p_user = link.parent
            if not p_user or p_user.id in seen_parents:
                continue
            seen_parents.add(p_user.id)

            report = dispatch_multi_channel_notification(
                db=db,
                school_id=user.school_id,
                user_id=p_user.id,
                title=title,
                message=message,
                event_type="BROADCAST_ALERT",
                phone=p_user.phone or s.father_phone,
                email=p_user.email,
                payload={"target_audience": target_audience, "sender": user.full_name or user.email},
            )

            sent_count += 1
            if report.get("whatsapp"):
                wa_sent += 1
            elif "opted out" in str(report.get("whatsapp_skipped_reason")):
                wa_opted_out += 1

            if report.get("email"):
                email_sent += 1
            elif "opted out" in str(report.get("email_skipped_reason")):
                email_opted_out += 1

    return {
        "success": True,
        "message": f"Broadcast delivered to {sent_count} parents.",
        "summary": {
            "total_recipients": sent_count,
            "in_app_delivered": sent_count,
            "whatsapp_delivered": wa_sent,
            "whatsapp_opted_out": wa_opted_out,
            "email_delivered": email_sent,
            "email_opted_out": email_opted_out,
        }
    }
