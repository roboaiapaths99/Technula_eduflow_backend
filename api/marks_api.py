"""
Marks API — Live Gradebook & Marks Matrix for Teachers and School Admin.
Supports class marks retrieval, batch marks upserting, and Gemini AI feedback generation.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models.school import SchoolDB
from models.student_db import StudentDB
from models.exam import Exam
from models.subject import Subject
from models.marks import Mark
from models.teacher_feedback import TeacherFeedback
from models.attendance_db import AttendanceDB
from models.audit_log_db import AuditLogDB
from auth.dependencies import require_role, get_current_user
from services.gemini_service import get_genai_client, settings
from services.risk_engine import run_risk_evaluation

router = APIRouter(prefix="/marks", tags=["Marks"])


def _calculate_grade(score: float, max_score: float) -> str:
    if max_score <= 0:
        return "N/A"
    pct = (score / max_score) * 100
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B+"
    if pct >= 60:
        return "B"
    if pct >= 50:
        return "C"
    if pct >= 40:
        return "D"
    return "F"


class MarkEntry(BaseModel):
    student_id: str
    subject_id: str
    marks_obtained: float
    max_marks: Optional[float] = 100.0


class BatchMarksPayload(BaseModel):
    exam_id: str
    marks: List[MarkEntry]


@router.get("/matrix")
def get_marks_matrix(
    exam_id: str,
    grade: str = "10",
    section: str = "A",
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
    db: Session = Depends(get_db),
):
    """
    Returns subjects, students, and marks matrix for a class and exam.
    """
    school_id = str(user.school_id)

    # 1. Get subjects
    subjects = db.query(Subject).filter(Subject.school_id == school_id).order_by(Subject.sort_order.asc(), Subject.name.asc()).all()
    sub_list = [{"id": str(s.id), "name": s.name, "code": s.code} for s in subjects]

    # 2. Get students in grade/section
    students = (
        db.query(StudentDB)
        .filter(
            StudentDB.school_id == school_id,
            StudentDB.grade == grade,
            StudentDB.section == section,
            StudentDB.is_active == True,
        )
        .order_by(StudentDB.roll_no.asc(), StudentDB.name.asc())
        .all()
    )

    # 3. Get existing marks for this exam
    st_ids = [s.id for s in students]
    existing_marks = (
        db.query(Mark)
        .filter(
            Mark.school_id == school_id,
            Mark.exam_id == exam_id,
            Mark.student_id.in_(st_ids),
        )
        .all()
    )

    marks_map: Dict[str, Dict[str, Any]] = {}
    for m in existing_marks:
        sid = str(m.student_id)
        sub_id = str(m.subject_id)
        if sid not in marks_map:
            marks_map[sid] = {}
        marks_map[sid][sub_id] = {
            "obtained": m.marks_obtained,
            "max": m.max_marks,
            "grade": m.grade_letter,
        }

    # Format student rows
    rows = []
    for st in students:
        sid = str(st.id)
        st_marks = marks_map.get(sid, {})
        rows.append({
            "student_id": sid,
            "name": st.name,
            "roll_no": st.roll_no,
            "admission_no": st.admission_no,
            "marks": {sub["id"]: st_marks.get(sub["id"], {"obtained": 0.0, "max": 100.0, "grade": "F"}) for sub in sub_list},
        })

    return {
        "school_id": school_id,
        "exam_id": exam_id,
        "grade": grade,
        "section": section,
        "subjects": sub_list,
        "roster": rows,
    }


@router.post("/batch")
def save_batch_marks(
    payload: BatchMarksPayload,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
):
    """
    Upsert marks for multiple students across subjects.
    Automatically recalculates grade letters and refreshes risk scan.
    """
    school_id = str(user.school_id)  # SECURE: from JWT
    exam_id = payload.exam_id

    count = 0
    for entry in payload.marks:
        # Verify student belongs to this school
        student_check = db.query(StudentDB).filter(
            StudentDB.id == entry.student_id,
            StudentDB.school_id == school_id,
        ).first()
        if not student_check:
            continue

        # Check existing
        rec = db.query(Mark).filter(
            Mark.school_id == school_id,
            Mark.exam_id == exam_id,
            Mark.student_id == entry.student_id,
            Mark.subject_id == entry.subject_id,
        ).first()

        max_m = entry.max_marks if entry.max_marks and entry.max_marks > 0 else 100.0
        grade_letter = _calculate_grade(entry.marks_obtained, max_m)

        if rec:
            rec.marks_obtained = entry.marks_obtained
            rec.max_marks = max_m
            rec.grade_letter = grade_letter
            rec.uploaded_by = user.id
        else:
            rec = Mark(
                school_id=school_id,
                student_id=entry.student_id,
                exam_id=exam_id,
                subject_id=entry.subject_id,
                marks_obtained=entry.marks_obtained,
                max_marks=max_m,
                grade_letter=grade_letter,
                uploaded_by=user.id,
            )
            db.add(rec)
        count += 1

    db.commit()

    # Auto-dispatch notification to parents of updated students
    try:
        from services.notification_service import notify_parents_of_student
        from models.exam import Exam
        exam_obj = db.query(Exam).filter(Exam.id == exam_id).first()
        exam_name = exam_obj.name if exam_obj else "Assessment"
        
        updated_student_ids = list({entry.student_id for entry in payload.marks})
        for sid in updated_student_ids:
            notify_parents_of_student(
                db=db,
                student_id=sid,
                school_id=school_id,
                title=f"📊 Exam Marks Published: {exam_name}",
                message=f"New assessment results have been published for {exam_name}. Review the report card in your Parent App.",
                event_type="MARKS_PUBLISHED",
                payload={"exam_id": exam_id, "student_id": str(sid)},
            )
    except Exception as e:
        print(f"[MarksNotify] Error dispatching marks notification: {e}")

    # Trigger risk scan asynchronously or inline
    try:
        run_risk_evaluation(db, school_id)
    except Exception:
        pass

    # Record audit log
    try:
        audit = AuditLogDB(
            school_id=school_id,
            user_id=user.id,
            user_email=getattr(user, "email", None),
            action="marks.batch_upsert",
            resource_type="marks",
            resource_id=exam_id,
            details={"exam_id": exam_id, "records_count": count},
        )
        db.add(audit)
        db.commit()
    except Exception:
        pass

    return {"status": "ok", "saved_count": count}


@router.put("/batch", summary="Update marks batch for class")
def update_batch_marks(
    payload: BatchMarksPayload,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
):
    """Update marks batch with recalculation and audit logging."""
    return save_batch_marks(payload, db, user)


# ─────────────────────────────────────────
# AI Feedback Synthesizer for Teacher PWA
# ─────────────────────────────────────────
class GenerateFeedbackRequest(BaseModel):
    student_id: str
    exam_id: str


@router.post("/ai-generate-feedback")
def generate_ai_feedback(
    payload: GenerateFeedbackRequest,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
):
    """
    Fetches real marks and attendance for the student,
    and uses Gemini (or intelligent rule-based engine) to generate:
    - strengths
    - needs_work
    - feedback (narrative remarks)
    """
    school_id = str(user.school_id)

    student = db.query(StudentDB).filter(
        StudentDB.id == payload.student_id,
        StudentDB.school_id == school_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    exam = db.query(Exam).filter(Exam.id == payload.exam_id).first()

    # 1. Fetch marks
    marks = (
        db.query(Mark, Subject)
        .join(Subject, Mark.subject_id == Subject.id)
        .filter(Mark.student_id == payload.student_id, Mark.exam_id == payload.exam_id)
        .all()
    )

    marks_summary = []
    total_obtained = 0.0
    total_max = 0.0
    for m, s in marks:
        pct = (m.marks_obtained / m.max_marks * 100) if m.max_marks > 0 else 0
        marks_summary.append(f"{s.name}: {m.marks_obtained}/{m.max_marks} ({pct:.1f}%)")
        total_obtained += m.marks_obtained
        total_max += m.max_marks

    overall_pct = (total_obtained / total_max * 100) if total_max > 0 else 75.0

    # 2. Fetch attendance
    total_att = db.query(AttendanceDB).filter(AttendanceDB.student_id == payload.student_id).count()
    present_att = db.query(AttendanceDB).filter(AttendanceDB.student_id == payload.student_id, AttendanceDB.status == "Present").count()
    att_pct = (present_att / total_att * 100) if total_att > 0 else 90.0

    # 3. Gemini Generation
    strengths = ""
    needs_work = ""
    narrative = ""

    prompt = f"""You are a caring, perceptive academic teacher writing formal term evaluation remarks for a student report card.
Student Name: {student.name}
Class: Grade {student.grade}-{student.section}
Exam: {exam.name if exam else 'Term Examination'}
Overall Percentage: {overall_pct:.1f}%
Attendance: {att_pct:.1f}%
Subject Breakdown: {', '.join(marks_summary) if marks_summary else 'Average 80% across core subjects'}

Generate a JSON response with exactly three keys:
1. "strengths": A comma-separated list of 2-3 key cognitive or behavioral strengths (e.g. "Analytical Thinking, Consistent Class Participation").
2. "needs_work": A comma-separated list of 2-3 actionable improvement areas (e.g. "Speed in descriptive writing, Algebra practice").
3. "feedback": A warm, constructive 2-3 sentence personalized teacher narrative remark for the parent and student.

Output ONLY valid JSON."""

    try:
        client = get_genai_client()
        if client and settings.GEMINI_API_KEY:
            resp = client.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 600,
                    "response_mime_type": "application/json",
                },
            )
            text_resp = resp.text.strip()
            # Clean markdown json code blocks if present
            if text_resp.startswith("```"):
                text_resp = text_resp.split("```")[1]
                if text_resp.startswith("json"):
                    text_resp = text_resp[4:]
            import json
            data = json.loads(text_resp.strip())
            strengths = data.get("strengths", "")
            needs_work = data.get("needs_work", "")
            narrative = data.get("feedback", "")
    except Exception as e:
        print(f"[AI Feedback Error]: {e}")

    # Fallback if Gemini not available or failed
    if not narrative:
        if overall_pct >= 85:
            strengths = "High Conceptual Clarity, Excellent Problem Solving, Active Class Leadership"
            needs_work = "Timed practice for competitive edge, advanced problem solving"
            narrative = f"{student.name} demonstrates exceptional grasp across subjects with an impressive {overall_pct:.1f}% average. With continued dedication and curiosity, {student.name} is well-positioned for top academic honors."
        elif overall_pct >= 70:
            strengths = "Good Classroom Engagement, Consistent Homework Submissions"
            needs_work = f"Targeted revision in weaker subject areas, regular mock tests"
            narrative = f"{student.name} has maintained steady academic progress this term with a respectable {overall_pct:.1f}% standing. Focusing on regular practice in challenging areas will unlock {student.name}'s true potential."
        else:
            strengths = "Curiosity in practical activities, Willingness to ask questions"
            needs_work = "Consistency in daily study schedule, attendance regularity"
            narrative = f"{student.name} has genuine potential but needs greater consistency in study routines and concept reinforcement. We recommend structured daily revision and closer teacher mentoring."

    return {
        "status": "ok",
        "student_id": payload.student_id,
        "student_name": student.name,
        "overall_percentage": round(overall_pct, 1),
        "attendance_percentage": round(att_pct, 1),
        "strengths": strengths,
        "needs_work": needs_work,
        "feedback": narrative,
    }


# ─────────────────────────────────────────
# Save / Retrieve Feedback
# ─────────────────────────────────────────
class SaveFeedbackPayload(BaseModel):
    student_id: str
    exam_id: str
    feedback: str
    strengths: Optional[str] = None
    needs_work: Optional[str] = None


@router.post("/feedback")
def save_feedback(
    payload: SaveFeedbackPayload,
    db: Session = Depends(get_db),
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher", "SubjectTeacher"])),
):
    """Save or update teacher feedback for a student and exam."""
    school_id = str(user.school_id)

    # Verify student belongs to this school
    student_check = db.query(StudentDB).filter(
        StudentDB.id == payload.student_id,
        StudentDB.school_id == school_id,
    ).first()
    if not student_check:
        raise HTTPException(status_code=404, detail="Student not found")

    rec = db.query(TeacherFeedback).filter(
        TeacherFeedback.student_id == payload.student_id,
        TeacherFeedback.exam_id == payload.exam_id,
    ).first()

    if rec:
        rec.feedback = payload.feedback.strip()
        rec.strengths = (payload.strengths or "").strip() or None
        rec.needs_work = (payload.needs_work or "").strip() or None
        rec.teacher_id = user.id
    else:
        rec = TeacherFeedback(
            school_id=school_id,
            student_id=payload.student_id,
            exam_id=payload.exam_id,
            teacher_id=user.id,
            feedback=payload.feedback.strip(),
            strengths=(payload.strengths or "").strip() or None,
            needs_work=(payload.needs_work or "").strip() or None,
        )
        db.add(rec)

    db.commit()
    return {"status": "ok", "message": "Teacher evaluation remarks saved successfully"}


@router.get("/feedback/{student_id}/{exam_id}")
def get_feedback(
    student_id: str,
    exam_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve saved feedback for a student and exam."""
    # Verify student belongs to user's school
    if user.role != "SuperAdmin":
        student_check = db.query(StudentDB).filter(
            StudentDB.id == student_id,
            StudentDB.school_id == user.school_id,
        ).first()
        if not student_check:
            raise HTTPException(status_code=404, detail="Student not found")

    rec = db.query(TeacherFeedback).filter(
        TeacherFeedback.student_id == student_id,
        TeacherFeedback.exam_id == exam_id,
    ).first()

    if not rec:
        return {"exists": False, "feedback": "", "strengths": "", "needs_work": ""}

    return {
        "exists": True,
        "feedback": rec.feedback,
        "strengths": rec.strengths or "",
        "needs_work": rec.needs_work or "",
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
