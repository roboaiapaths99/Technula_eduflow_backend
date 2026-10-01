from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session

from services.analytics_service import (
    compute_dashboard,
    compute_parent_class_insights,
    get_student,
)

from auth.dependencies import require_role, get_db
from models.parent_student_db import ParentStudentDB
from models.teacher_assignment_db import TeacherAssignmentDB

router = APIRouter()


def _enforce_student_access(user, student, db: Session):
    role = (getattr(user, "role", "") or "").lower()
    if role == "admin":
        return

    if role == "parent":
        ok = (
            db.query(ParentStudentDB)
            .filter(
                ParentStudentDB.parent_user_id == user.id,
                ParentStudentDB.student_id == student.id,
            )
            .first()
        )
        if not ok:
            raise HTTPException(status_code=403, detail="Forbidden")

    if role == "teacher":
        ok = (
            db.query(TeacherAssignmentDB)
            .filter(
                TeacherAssignmentDB.teacher_user_id == user.id,
                TeacherAssignmentDB.grade == str(student.grade),
                TeacherAssignmentDB.section == str(student.section),
            )
            .first()
        )
        if not ok:
            raise HTTPException(status_code=403, detail="Forbidden")


# ──────────────────────────────────────────
# EXISTING ENDPOINT (KEEP AS IS) – now ownership-protected
# Used by current MVP dashboard
# ──────────────────────────────────────────
@router.get("/{student_id}", summary="Get dashboard data for a student (alias)")
@router.get("/{student_id}/dashboard-data", summary="Get dashboard data for a student")
def get_dashboard_data(
    student_id: int,
    user=Depends(require_role(["Parent", "Teacher", "Admin"])),
    db: Session = Depends(get_db),
):
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    _enforce_student_access(user, student, db)

    return compute_dashboard(student_id)


# ──────────────────────────────────────────
# NEW ENDPOINT (Parent + Class Insights)
# ──────────────────────────────────────────
@router.get("/parent/{student_id}", summary="Get parent dashboard (student + class insights)")
def get_parent_dashboard(
    student_id: int,
    exam_name: str = Query("Final"),
    user=Depends(require_role(["Parent", "Teacher", "Admin"])),
    db: Session = Depends(get_db),
):
    """
    Combines:
    - student dashboard data
    - class comparison insights (for selected exam)
    """
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    _enforce_student_access(user, student, db)

    base = compute_dashboard(student_id)
    class_insights = compute_parent_class_insights(
        student_id=student_id,
        exam_name=exam_name,
    )

    return {
        **base,
        **class_insights,
    }
