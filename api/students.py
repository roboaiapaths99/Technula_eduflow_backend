from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from db.session import get_db
from models.student_db import StudentDB
from models.parent_student_db import ParentStudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from auth.dependencies import require_role

router = APIRouter()


@router.get("/", summary="List students")
@router.get("", summary="List students")
def list_students_endpoint(
    school_id: Optional[str] = None,
    user=Depends(require_role(["Parent", "Teacher", "ClassTeacher", "SubjectTeacher", "Admin"])),
    db: Session = Depends(get_db),
):
    role = (getattr(user, "role", "") or "").lower()
    query = db.query(StudentDB).filter(StudentDB.is_active == True)

    effective_school_id = school_id or user.school_id
    if effective_school_id:
        query = query.filter(StudentDB.school_id == effective_school_id)

    if role == "admin":
        students = query.order_by(StudentDB.roll_no.asc(), StudentDB.name.asc()).all()
    elif role == "parent":
        mapped_ids = {
            r.student_id
            for r in db.query(ParentStudentDB)
            .filter(ParentStudentDB.parent_user_id == user.id)
            .all()
        }
        students = query.filter(StudentDB.id.in_(mapped_ids)).all()
    else:  # teachers
        assigns = db.query(TeacherAssignmentDB).filter(
            TeacherAssignmentDB.teacher_user_id == user.id
        ).all()
        allowed = {(str(a.grade), str(a.section)) for a in assigns}
        all_s = query.all()
        students = [s for s in all_s if (str(s.grade), str(s.section)) in allowed]

    return [
        {
            "id": str(s.id),
            "name": s.name,
            "admission_no": s.admission_no,
            "roll_no": s.roll_no,
            "grade": s.grade,
            "section": s.section,
            "gender": s.gender,
        }
        for s in students
    ]
