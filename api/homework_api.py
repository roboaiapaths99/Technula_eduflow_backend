"""
Homework and Assignment Diary API.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from models.homework_db import HomeworkDB, HomeworkSubmissionDB
from models.subject import Subject
from models.student_db import StudentDB
from models.user_db import UserDB
from models.parent_student_db import ParentStudentDB
from auth.dependencies import require_role, get_current_user

router = APIRouter(prefix="/homework", tags=["Homework Diary"])


@router.post("/")
def create_homework(
    payload: dict,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)  # SECURE: from JWT
    grade = payload.get("grade")
    section = (payload.get("section") or "A").upper()
    subject_id = payload.get("subject_id")
    title = payload.get("title")
    description = payload.get("description", "")
    due_date_str = payload.get("due_date")
    priority = payload.get("priority", "MEDIUM")
    attachment_url = payload.get("attachment_url")

    if not grade or not subject_id or not title or not due_date_str:
        raise HTTPException(status_code=400, detail="Missing required homework fields")

    due_d = datetime.strptime(due_date_str, "%Y-%m-%d").date()

    hw = HomeworkDB(
        school_id=school_id,
        grade=grade,
        section=section,
        subject_id=subject_id,
        posted_by=user.id,  # from JWT user
        title=title,
        description=description,
        due_date=due_d,
        priority=priority,
        attachment_url=attachment_url,
        is_active=True,
    )
    db.add(hw)
    db.commit()
    db.refresh(hw)

    # Multi-channel auto-dispatch to parents of this class
    try:
        from models.parent_student_db import ParentStudentDB
        from models.user_db import UserDB
        from services.notification_service import dispatch_multi_channel_notification
        subject = db.query(Subject).filter(Subject.id == subject_id).first()
        subj_name = subject.name if subject else "Academic"

        class_students = db.query(StudentDB.id).filter(
            StudentDB.school_id == school_id,
            StudentDB.current_class == grade,
            StudentDB.section == section,
            StudentDB.is_active == True
        ).all()
        student_ids = [s[0] for s in class_students]

        if student_ids:
            parents = (
                db.query(UserDB)
                .join(ParentStudentDB, ParentStudentDB.parent_user_id == UserDB.id)
                .filter(ParentStudentDB.student_id.in_(student_ids))
                .all()
            )
            seen_parent_ids = set()
            for p in parents:
                if p.id not in seen_parent_ids:
                    seen_parent_ids.add(p.id)
                    dispatch_multi_channel_notification(
                        db=db,
                        school_id=school_id,
                        user_id=p.id,
                        title=f"📚 New Homework: {subj_name}",
                        message=f"{title} (Due: {due_date_str})",
                        event_type="HOMEWORK_ASSIGNED",
                        phone=p.phone,
                        email=p.email,
                        payload={"homework_id": str(hw.id), "grade": grade, "section": section},
                    )
    except Exception as e:
        print(f"[Notification] Homework dispatch notice: {e}")

    return {"status": "ok", "id": str(hw.id), "message": "Homework assigned successfully"}


@router.get("/class")
def get_class_homework(
    grade: str = "10",
    section: str = "A",
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    school_id = str(user.school_id)

    homeworks = db.query(HomeworkDB).filter(
        HomeworkDB.school_id == school_id,
        HomeworkDB.grade == grade,
        HomeworkDB.section == section,
        HomeworkDB.is_active == True
    ).order_by(HomeworkDB.due_date.desc()).all()

    total_class_students = db.query(StudentDB).filter(
        StudentDB.school_id == school_id,
        StudentDB.grade == grade,
        StudentDB.section == section,
        StudentDB.is_active == True
    ).count() or 1

    results = []
    for hw in homeworks:
        subject = db.query(Subject).filter(Subject.id == hw.subject_id).first()
        teacher = db.query(UserDB).filter(UserDB.id == hw.posted_by).first()

        submitted_count = db.query(HomeworkSubmissionDB).filter(
            HomeworkSubmissionDB.homework_id == hw.id,
            HomeworkSubmissionDB.status.in_(["SUBMITTED", "GRADED"])
        ).count()

        results.append({
            "id": str(hw.id),
            "title": hw.title,
            "description": hw.description,
            "subject_name": subject.name if subject else "General",
            "teacher_name": teacher.full_name if teacher else "Faculty",
            "due_date": str(hw.due_date),
            "priority": hw.priority,
            "attachment_url": hw.attachment_url,
            "submitted_count": submitted_count,
            "total_students": total_class_students,
            "completion_rate": round((submitted_count / total_class_students) * 100.0, 1),
            "is_overdue": date.today() > hw.due_date,
        })

    return results


@router.get("/student/{student_id}")
def get_student_homework(
    student_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Verify student access
    if user.role != "SuperAdmin":
        if (user.role or "").strip().lower() in ["parent", "student"]:
            link = db.query(ParentStudentDB).filter(
                ParentStudentDB.parent_user_id == user.id,
                ParentStudentDB.student_id == student_id,
            ).first()
            if not link and user.school_id and str(student.school_id) != str(user.school_id):
                raise HTTPException(status_code=403, detail="You do not have access to this student's records")
        elif user.school_id and str(student.school_id) != str(user.school_id):
            raise HTTPException(status_code=403, detail="Access denied")

    homeworks = db.query(HomeworkDB).filter(
        HomeworkDB.school_id == student.school_id,
        HomeworkDB.grade == student.grade,
        HomeworkDB.section == student.section,
        HomeworkDB.is_active == True
    ).order_by(HomeworkDB.due_date.desc()).all()

    results = []
    for hw in homeworks:
        subject = db.query(Subject).filter(Subject.id == hw.subject_id).first()
        teacher = db.query(UserDB).filter(UserDB.id == hw.posted_by).first()
        submission = db.query(HomeworkSubmissionDB).filter(
            HomeworkSubmissionDB.homework_id == hw.id,
            HomeworkSubmissionDB.student_id == student_id
        ).first()

        raw_status = submission.status if submission else "NOT_SUBMITTED"
        is_overdue = date.today() > hw.due_date and raw_status == "NOT_SUBMITTED"

        if submission and submission.status in ["SUBMITTED", "GRADED"]:
            sub_status = "Submitted"
        elif submission and submission.status == "LATE":
            sub_status = "Late"
        elif is_overdue:
            sub_status = "Overdue"
        else:
            sub_status = "Pending Submission"

        results.append({
            "id": str(hw.id),
            "title": hw.title,
            "description": hw.description,
            "subject_name": subject.name if subject else "General",
            "teacher_name": teacher.full_name if teacher else "Faculty",
            "due_date": str(hw.due_date),
            "priority": hw.priority,
            "attachment_url": hw.attachment_url,
            "status": "OVERDUE" if is_overdue else raw_status,
            "submission_status": sub_status,
            "grade": submission.grade_value if submission else None,
            "grade_value": submission.grade_value if submission else None,
            "is_overdue": is_overdue,
            "submitted_at": submission.submitted_at.isoformat() if (submission and submission.submitted_at) else None,
            "remarks": submission.remarks if submission else None,
        })

    return results


@router.get("/{homework_id}/submissions")
def get_homework_submissions(
    homework_id: str,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Returns submission checklist for all students in the assigned class."""
    hw = db.query(HomeworkDB).filter(HomeworkDB.id == homework_id).first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")

    # Verify homework belongs to user's school
    if user.role != "SuperAdmin" and str(hw.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    students = db.query(StudentDB).filter(
        StudentDB.school_id == hw.school_id,
        StudentDB.grade == hw.grade,
        StudentDB.section == hw.section,
        StudentDB.is_active == True,
    ).order_by(StudentDB.roll_no.asc()).all()

    existing_subs = {
        s.student_id: s
        for s in db.query(HomeworkSubmissionDB).filter(HomeworkSubmissionDB.homework_id == homework_id).all()
    }

    results = []
    for st in students:
        sub = existing_subs.get(st.id)
        results.append({
            "student_id": str(st.id),
            "student_name": st.name,
            "roll_no": st.roll_no,
            "status": sub.status if sub else "NOT_SUBMITTED",
            "submitted_at": str(sub.submitted_at) if sub and sub.submitted_at else None,
            "remarks": sub.remarks if sub else "",
            "grade_value": sub.grade_value if sub else "",
        })

    return {
        "homework_id": homework_id,
        "title": hw.title,
        "due_date": str(hw.due_date),
        "total_students": len(students),
        "submitted_count": sum(1 for r in results if r["status"] in ["SUBMITTED", "GRADED"]),
        "submissions": results,
    }


@router.post("/{homework_id}/submissions")
def update_submissions(
    homework_id: str,
    payload: dict,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Teacher updates submission checklist for students."""
    hw = db.query(HomeworkDB).filter(HomeworkDB.id == homework_id).first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")

    if user.role != "SuperAdmin" and str(hw.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    submissions_data = payload.get("submissions", [])

    for item in submissions_data:
        st_id = item.get("student_id")
        status = item.get("status", "SUBMITTED")
        remarks = item.get("remarks")

        existing = db.query(HomeworkSubmissionDB).filter(
            HomeworkSubmissionDB.homework_id == homework_id,
            HomeworkSubmissionDB.student_id == st_id,
        ).first()

        if existing:
            existing.status = status
            existing.remarks = remarks
            if status in ["SUBMITTED", "LATE"] and not existing.submitted_at:
                existing.submitted_at = datetime.now()
        else:
            sub = HomeworkSubmissionDB(
                homework_id=homework_id,
                student_id=st_id,
                status=status,
                remarks=remarks,
                submitted_at=datetime.now() if status in ["SUBMITTED", "LATE"] else None,
            )
            db.add(sub)

    db.commit()
    return {"status": "ok", "message": f"Updated {len(submissions_data)} submissions"}


@router.put("/{homework_id}")
def update_homework(
    homework_id: str,
    payload: dict,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Update homework title, description, due date."""
    hw = db.query(HomeworkDB).filter(HomeworkDB.id == homework_id).first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")

    if user.role != "SuperAdmin" and str(hw.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if "title" in payload and payload["title"]:
        hw.title = payload["title"].strip()
    if "description" in payload:
        hw.description = (payload["description"] or "").strip()
    if "due_date" in payload and payload["due_date"]:
        hw.due_date = datetime.strptime(payload["due_date"], "%Y-%m-%d").date()
    if "subject_name" in payload:
        hw.subject_name = payload["subject_name"]

    db.commit()
    return {"status": "ok", "message": f"Homework '{hw.title}' updated"}


@router.delete("/{homework_id}")
def delete_homework(
    homework_id: str,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """Delete a homework assignment."""
    hw = db.query(HomeworkDB).filter(HomeworkDB.id == homework_id).first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")

    if user.role != "SuperAdmin" and str(hw.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete submissions first
    db.query(HomeworkSubmissionDB).filter(HomeworkSubmissionDB.homework_id == homework_id).delete()
    db.delete(hw)
    db.commit()
    return {"status": "ok", "message": f"Homework '{hw.title}' deleted"}
