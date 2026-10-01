"""
Student Communication Diary API.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import date as dt_date, datetime, timezone
from typing import Optional, List
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from models.student_diary_db import StudentDiaryEntryDB
from models.student_db import StudentDB
from models.user_db import UserDB
from models.school import SchoolDB
from models.parent_student_db import ParentStudentDB
from services.notification_service import create_in_app_notification, send_whatsapp_message
from auth.dependencies import require_role, get_current_user
from auth.plan_guard import require_feature

logger = logging.getLogger("api.diary")

router = APIRouter(
    prefix="/diary",
    tags=["Student Diary"],
    dependencies=[Depends(require_feature("chat_diary"))],
)


class CreateDiaryEntryRequest(BaseModel):
    student_id: str
    category: str = "APPRECIATION"
    title: Optional[str] = None
    remark: str
    action_required: bool = False
    is_parent_visible: bool = True
    entry_date: Optional[dt_date] = None


@router.post("/")
def create_diary_entry(
    req: CreateDiaryEntryRequest,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Teacher creates a diary remark for a student."""
    school_id = str(user.school_id)  # SECURE: from JWT

    student = db.query(StudentDB).filter(
        StudentDB.id == req.student_id,
        StudentDB.school_id == school_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    teacher_name = user.full_name or "Class Teacher"

    entry = StudentDiaryEntryDB(
        school_id=school_id,
        student_id=req.student_id,
        teacher_user_id=user.id,
        entry_date=req.entry_date or dt_date.today(),
        category=req.category.upper(),
        title=req.title,
        remark=req.remark.strip(),
        action_required=req.action_required,
        is_parent_visible=req.is_parent_visible,
        acknowledged_by_parent=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # If visible to parent, send multi-channel notification to linked parents
    if req.is_parent_visible:
        try:
            from services.notification_service import notify_parents_of_student
            action_tag = "⚠️ [Action Required] " if req.action_required else ""
            notify_parents_of_student(
                db=db,
                student_id=student.id,
                school_id=school_id,
                title=f"📝 {action_tag}Diary Entry: {req.title}",
                message=f"Teacher {teacher_name} noted: \"{entry.remark}\"",
                event_type="DIARY_ENTRY",
                payload={"entry_id": str(entry.id), "student_id": str(student.id), "action_required": req.action_required},
            )
        except Exception as e:
            logger.warning(f"Failed to dispatch diary notification: {e}")

    return {
        "status": "success",
        "id": str(entry.id),
        "message": "Diary entry recorded successfully",
    }


@router.get("/student/{student_id}")
def get_student_diary(
    student_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch chronological diary entries for a student."""
    if user.role != "SuperAdmin":
        student = db.query(StudentDB).filter(
            StudentDB.id == student_id,
            StudentDB.school_id == user.school_id,
        ).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

    entries = (
        db.query(StudentDiaryEntryDB)
        .filter(StudentDiaryEntryDB.student_id == student_id)
        .order_by(StudentDiaryEntryDB.entry_date.desc(), StudentDiaryEntryDB.created_at.desc())
        .all()
    )

    results = []
    for e in entries:
        t_name = e.teacher.full_name if e.teacher else "Teacher"
        results.append({
            "id": str(e.id),
            "school_id": str(e.school_id),
            "student_id": str(e.student_id),
            "teacher_user_id": str(e.teacher_user_id),
            "teacher_name": t_name,
            "category": e.category,
            "title": e.title,
            "remark": e.remark,
            "entry_date": e.entry_date.isoformat() if e.entry_date else None,
            "action_required": e.action_required,
            "is_parent_visible": e.is_parent_visible,
            "acknowledged_by_parent": e.acknowledged_by_parent,
            "acknowledged_at": e.acknowledged_at.isoformat() if e.acknowledged_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return results


@router.get("/class")
def get_class_diary_entries(
    grade: str,
    section: str,
    date: Optional[dt_date] = None,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Fetch diary remarks for all students in a class."""
    school_id = str(user.school_id)

    students = (
        db.query(StudentDB)
        .filter(
            StudentDB.school_id == school_id,
            StudentDB.grade == grade,
            StudentDB.section == section,
            StudentDB.is_active == True,
        )
        .all()
    )
    student_map = {s.id: s for s in students}
    student_ids = list(student_map.keys())

    query = db.query(StudentDiaryEntryDB).filter(
        StudentDiaryEntryDB.school_id == school_id,
        StudentDiaryEntryDB.student_id.in_(student_ids) if student_ids else False,
    )
    if date:
        query = query.filter(StudentDiaryEntryDB.entry_date == date)

    entries = query.order_by(StudentDiaryEntryDB.entry_date.desc(), StudentDiaryEntryDB.created_at.desc()).all()

    return [
        {
            "id": str(e.id),
            "student_id": str(e.student_id),
            "student_name": student_map[e.student_id].name if e.student_id in student_map else "Student",
            "roll_no": student_map[e.student_id].roll_no if e.student_id in student_map else "-",
            "category": e.category,
            "title": e.title,
            "remark": e.remark,
            "entry_date": e.entry_date.isoformat() if e.entry_date else None,
            "action_required": e.action_required,
            "acknowledged_by_parent": e.acknowledged_by_parent,
            "teacher_name": e.teacher.full_name if e.teacher else "Teacher",
        }
        for e in entries
    ]


@router.patch("/{entry_id}/acknowledge")
def acknowledge_diary_entry(
    entry_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parent formally marks a diary remark as reviewed and acknowledged."""
    entry = db.query(StudentDiaryEntryDB).filter(StudentDiaryEntryDB.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    if user.role != "SuperAdmin" and str(entry.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    entry.acknowledged_by_parent = True
    entry.acknowledged_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "success",
        "entry_id": str(entry.id),
        "acknowledged_at": entry.acknowledged_at.isoformat(),
        "message": "Diary remark acknowledged successfully",
    }


@router.delete("/{entry_id}")
def delete_diary_entry(
    entry_id: str,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """Delete a diary entry."""
    entry = db.query(StudentDiaryEntryDB).filter(StudentDiaryEntryDB.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Diary entry not found")

    if user.role != "SuperAdmin" and str(entry.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(entry)
    db.commit()
    return {"status": "success", "message": "Diary entry deleted"}
