from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from services.analytics_service import (
    compute_dashboard,
    compute_parent_class_insights,
    get_student,
)
from services.llm_service import generate_academic_summary

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


@router.post("/{student_id}/ai-insights", summary="Generate academic summary")
def get_ai_insights(
    student_id: int,
    user=Depends(require_role(["Parent", "Teacher", "Admin"])),
    db: Session = Depends(get_db),
):
    student = get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    _enforce_student_access(user, student, db)

    base = compute_dashboard(student_id)
    class_insights = compute_parent_class_insights(
        student_id=student_id,
        exam_name="Final",
    )

    teacher_feedback = base.get("teacher_feedback") or class_insights.get("teacher_feedback")

    dashboard_data = {
        **base,
        **class_insights,
        "teacher_feedback": teacher_feedback,
    }

    summary = generate_academic_summary(dashboard_data)
    return {"summary": summary}
