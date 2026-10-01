from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text, or_

from db.session import SessionLocal
from models.teacher_feedback import TeacherFeedback
from models.student_db import StudentDB
from models.teacher_assignment_db import TeacherAssignmentDB
from auth.dependencies import require_role

router = APIRouter()

# ✅ run migration once (per server process)
_MIGRATED = False


def _ensure_teacher_feedback_schema(db: Session) -> None:
    """
    ✅ Safe SQLite migration without data loss:
    - Adds teacher_user_id column if missing
    - Creates unique index (student_id, exam_id, teacher_user_id)
    Legacy rows keep teacher_user_id = NULL.
    """
    global _MIGRATED
    if _MIGRATED:
        return

    try:
        cols = db.execute(text("PRAGMA table_info(teacher_feedback)")).fetchall()
        col_names = {c[1] for c in cols}

        if "teacher_user_id" not in col_names:
            db.execute(text("ALTER TABLE teacher_feedback ADD COLUMN teacher_user_id INTEGER"))
            db.commit()

        db.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_feedback_student_exam_teacher "
                "ON teacher_feedback(student_id, exam_id, teacher_user_id)"
            )
        )
        db.commit()

        _MIGRATED = True
    except Exception:
        db.rollback()
        _MIGRATED = True


def get_db():
    db = SessionLocal()
    try:
        _ensure_teacher_feedback_schema(db)
        yield db
    finally:
        db.close()


class TeacherFeedbackUpsert(BaseModel):
    student_id: int
    exam_id: int
    remark: str
    note: Optional[str] = None


def _enforce_teacher_assignment(user, student: StudentDB, db: Session):
    role = (getattr(user, "role", "") or "").lower()
    if role == "admin":
        return

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
            raise HTTPException(status_code=403, detail="Teacher not assigned to this class")


@router.post("/feedback")
def upsert_teacher_feedback(
    payload: TeacherFeedbackUpsert,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Teacher", "Admin"])),
):
    if not (payload.remark or "").strip():
        raise HTTPException(status_code=400, detail="remark is required")

    student = db.query(StudentDB).filter(StudentDB.id == payload.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    _enforce_teacher_assignment(user, student, db)

    role = (getattr(user, "role", "") or "").lower()
    teacher_id = user.id if role == "teacher" else None

    # ✅ First try teacher-specific row
    row = (
        db.query(TeacherFeedback)
        .filter(
            TeacherFeedback.student_id == payload.student_id,
            TeacherFeedback.exam_id == payload.exam_id,
            TeacherFeedback.teacher_user_id == teacher_id,
        )
        .first()
    )

    # ✅ Backward-compatible: if not found, try legacy row (teacher_user_id IS NULL)
    if row is None and teacher_id is not None:
        row = (
            db.query(TeacherFeedback)
            .filter(
                TeacherFeedback.student_id == payload.student_id,
                TeacherFeedback.exam_id == payload.exam_id,
                TeacherFeedback.teacher_user_id.is_(None),
            )
            .first()
        )
        # If legacy row exists, "claim" it for this teacher
        if row is not None:
            row.teacher_user_id = teacher_id

    if row is None:
        row = TeacherFeedback(
            teacher_user_id=teacher_id,
            student_id=payload.student_id,
            exam_id=payload.exam_id,
            remark=payload.remark.strip(),
            note=(payload.note or "").strip() or None,
        )
        db.add(row)
    else:
        row.remark = payload.remark.strip()
        row.note = (payload.note or "").strip() or None

    db.commit()
    db.refresh(row)

    return {
        "item": {
            "teacher_user_id": row.teacher_user_id,
            "student_id": row.student_id,
            "exam_id": row.exam_id,
            "remark": row.remark,
            "note": row.note,
        }
    }


@router.get("/feedback")
def read_teacher_feedback(
    student_id: int,
    exam_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Teacher", "Admin","Parent"])),
):
    student = db.query(StudentDB).filter(StudentDB.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    _enforce_teacher_assignment(user, student, db)

    role = (getattr(user, "role", "") or "").lower()
    teacher_id = user.id if role == "teacher" else None

    # ✅ Teacher sees their feedback; fallback to legacy feedback if needed
    if teacher_id is not None:
        row = (
            db.query(TeacherFeedback)
            .filter(
                TeacherFeedback.student_id == student_id,
                TeacherFeedback.exam_id == exam_id,
                or_(
                    TeacherFeedback.teacher_user_id == teacher_id,
                    TeacherFeedback.teacher_user_id.is_(None),
                ),
            )
            # prefer teacher-specific if both exist
            .order_by(TeacherFeedback.teacher_user_id.desc())
            .first()
        )
    else:
        # Admin view: show any (prefer non-null)
        row = (
            db.query(TeacherFeedback)
            .filter(
                TeacherFeedback.student_id == student_id,
                TeacherFeedback.exam_id == exam_id,
            )
            .order_by(TeacherFeedback.teacher_user_id.desc())
            .first()
        )

    if not row:
        return {"item": None}

    return {
        "item": {
            "teacher_user_id": getattr(row, "teacher_user_id", None),
            "student_id": row.student_id,
            "exam_id": row.exam_id,
            "remark": row.remark,
            "note": row.note,
        }
    }
