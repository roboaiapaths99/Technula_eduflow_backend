"""
Birthday Engine API — Automated celebration wishes via In-App and WhatsApp.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract

from db.session import get_db
from models.student_db import StudentDB
from models.school import SchoolDB
from models.parent_student_db import ParentStudentDB
from models.user_db import UserDB
from auth.dependencies import get_current_user, require_role
from services.notification_service import dispatch_multi_channel_notification

router = APIRouter(prefix="/birthdays", tags=["Birthday Engine"])

DEFAULT_BIRTHDAY_TEMPLATE = "Dear Parent, {school_name} extends warmest wishes to {student_name} (Class {grade}) on their Birthday! May this year be filled with happiness, knowledge, and success! 🎂🎉"


@router.get("/today")
@router.get("/today/{school_id}")
def get_today_birthdays(
    school_id: Optional[str] = None,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target_school_id = school_id or user.school_id
    today = date.today()
    students = db.query(StudentDB).filter(
        StudentDB.school_id == target_school_id,
        StudentDB.is_active == True,
        StudentDB.dob != None,
        extract("month", StudentDB.dob) == today.month,
        extract("day", StudentDB.dob) == today.day,
    ).all()

    res = []
    for s in students:
        res.append({
            "student_id": str(s.id),
            "id": str(s.id),
            "name": s.name,
            "admission_no": s.admission_no,
            "grade": s.grade,
            "section": s.section,
            "photo_url": s.photo_url,
            "father_phone": s.father_phone,
            "mother_phone": s.mother_phone,
        })
    return {
        "count": len(res),
        "date": today.isoformat(),
        "birthdays": res,
    }


@router.post("/trigger-wishes")
def trigger_birthday_wishes(
    payload: dict = {},
    user: UserDB = Depends(require_role(["Admin", "Principal", "Vice_Principal", "Staff"])),
    db: Session = Depends(get_db),
):
    today = date.today()
    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    template = getattr(school, "birthday_template", None) or DEFAULT_BIRTHDAY_TEMPLATE

    students = db.query(StudentDB).filter(
        StudentDB.school_id == user.school_id,
        StudentDB.is_active == True,
        StudentDB.dob != None,
        extract("month", StudentDB.dob) == today.month,
        extract("day", StudentDB.dob) == today.day,
    ).all()

    dispatched = 0
    results = []

    for s in students:
        # Find linked parent user
        link = db.query(ParentStudentDB).filter(ParentStudentDB.student_id == s.id).first()
        parent_user_id = link.parent_user_id if link else None
        phone = (link.parent.phone if link and link.parent else None) or s.father_phone or s.mother_phone
        email = (link.parent.email if link and link.parent else None)

        msg = template.replace("{school_name}", school.name if school else "Technula EduFlow").replace(
            "{student_name}", s.name
        ).replace("{grade}", f"{s.grade}-{s.section}")

        report = dispatch_multi_channel_notification(
            db=db,
            school_id=user.school_id,
            user_id=parent_user_id,
            title=f"Happy Birthday {s.name}! 🎂",
            message=msg,
            event_type="BIRTHDAY_WISH",
            phone=phone,
            email=email,
            payload={"student_id": str(s.id), "student_name": s.name},
        )
        dispatched += 1
        results.append({
            "student_name": s.name,
            "phone": phone,
            "channels": report,
        })

    return {
        "success": True,
        "message": f"Birthday wishes processed for {dispatched} student(s) celebrating today.",
        "dispatched_count": dispatched,
        "details": results,
    }
