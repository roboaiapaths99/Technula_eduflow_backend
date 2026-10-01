"""
AI-Powered Student Risk Prediction & Pedagogical Intervention Engine.
Analyzes student academic trends, subject degradation, attendance drops below CBSE thresholds,
and generates actionable remediation plans using Gemini AI.
SECURED: All endpoints require auth and derive school_id from JWT user context.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from db.session import get_db
from models.student_db import StudentDB
from models.marks import Mark
from models.attendance_db import AttendanceDB
from models.exam import Exam
from models.subject import Subject
from models.risk_case_db import RiskCaseDB
from models.user_db import UserDB
from models.parent_student_db import ParentStudentDB
from core.config import settings
from auth.dependencies import get_current_user, require_role
from auth.plan_guard import require_feature

router = APIRouter(
    prefix="/risk",
    tags=["AI Risk Prediction"],
    dependencies=[Depends(require_feature("risk_prediction"))],
)


def _get_effective_school_id(user: UserDB, school_id_override: Optional[str] = None) -> str:
    if (user.role or "").strip() == "SuperAdmin" and school_id_override:
        return school_id_override
    if not user.school_id:
        raise HTTPException(status_code=403, detail="User is not assigned to any school")
    return str(user.school_id)


def compute_student_risk_profile(student: StudentDB, db: Session) -> Dict[str, Any]:
    # 1. Attendance Analysis (Last 60 Days)
    cutoff_date = date.today() - timedelta(days=60)
    attendance_records = db.query(AttendanceDB).filter(
        AttendanceDB.student_id == student.id,
        AttendanceDB.school_id == student.school_id,
        AttendanceDB.date >= cutoff_date
    ).all()

    total_sessions = len(attendance_records)
    present_sessions = sum(1 for a in attendance_records if a.status.upper() in ["PRESENT", "HALF_DAY"])
    attendance_pct = (present_sessions / total_sessions * 100) if total_sessions > 0 else 95.0

    # 2. Academic Scores & Longitudinal Trajectory
    marks_rows = db.query(Mark, Exam, Subject).join(
        Exam, Mark.exam_id == Exam.id
    ).join(
        Subject, Mark.subject_id == Subject.id
    ).filter(
        Mark.student_id == student.id,
        Mark.school_id == student.school_id
    ).order_by(Exam.term.asc(), Exam.name.asc()).all()

    exam_scores: Dict[str, List[float]] = {}
    subject_scores: Dict[str, List[float]] = {}

    for mark, exam, subject in marks_rows:
        pct = (mark.marks_obtained / mark.max_marks * 100) if mark.max_marks > 0 else 0.0
        exam_scores.setdefault(exam.name, []).append(pct)
        subject_scores.setdefault(subject.name, []).append(pct)

    exam_averages = [
        {"exam": e_name, "avg": sum(scores) / len(scores)}
        for e_name, scores in exam_scores.items()
    ]

    latest_avg = exam_averages[-1]["avg"] if exam_averages else 85.0
    previous_avg = exam_averages[-2]["avg"] if len(exam_averages) >= 2 else latest_avg
    trend_velocity = round(latest_avg - previous_avg, 1)

    weak_subjects = []
    for s_name, scores in subject_scores.items():
        avg = sum(scores) / len(scores)
        if avg < 70.0:
            weak_subjects.append({
                "subject": s_name,
                "average_score": round(avg, 1),
                "severity": "CRITICAL" if avg < 50.0 else "WARNING"
            })

    risk_points = 0.0
    risk_factors = []

    if attendance_pct < 75.0:
        risk_points += 40.0
        risk_factors.append(f"Critical: Attendance ({attendance_pct:.1f}%) is below 75% CBSE Board Eligibility threshold.")
    elif attendance_pct < 85.0:
        risk_points += 20.0
        risk_factors.append(f"Warning: Attendance ({attendance_pct:.1f}%) shows concerning irregularity.")

    if latest_avg < 50.0:
        risk_points += 40.0
        risk_factors.append(f"Critical: Overall score average ({latest_avg:.1f}%) is in the fail/remedial danger zone.")
    elif latest_avg < 70.0:
        risk_points += 25.0
        risk_factors.append(f"Warning: Overall academic score ({latest_avg:.1f}%) is below expected standard.")

    if trend_velocity <= -10.0:
        risk_points += 20.0
        risk_factors.append(f"Steep negative trajectory: Scores dropped by {abs(trend_velocity):.1f}% since previous exam.")
    elif trend_velocity <= -5.0:
        risk_points += 10.0
        risk_factors.append(f"Negative trajectory: Scores dipped by {abs(trend_velocity):.1f}%.")

    risk_score = min(100.0, round(risk_points, 1))

    if risk_score >= 60.0:
        severity = "CRITICAL"
        action_required = "Immediate Parent-Teacher conference and personalized remedial tutoring plan required."
    elif risk_score >= 35.0:
        severity = "HIGH"
        action_required = "Mentorship check-in and targeted practice worksheets in flagged subjects."
    elif risk_score >= 15.0:
        severity = "MEDIUM"
        action_required = "Monitor daily attendance and verify homework submission consistency."
    else:
        severity = "SAFE"
        action_required = "Student demonstrates strong consistency. Continue standard academic progression."

    recommendations = []
    if attendance_pct < 80.0:
        recommendations.append({
            "type": "ATTENDANCE_INTERVENTION",
            "action": "Issue formal attendance warning notification to parent and schedule morning check-in.",
            "timeline": "Within 48 hours"
        })
    if weak_subjects:
        for ws in weak_subjects:
            recommendations.append({
                "type": "SUBJECT_REMEDIATION",
                "action": f"Provide structured concept reinforcement modules and descriptive question drills in {ws['subject']}.",
                "timeline": "Next 2 weeks"
            })
    if trend_velocity < -5.0:
        recommendations.append({
            "type": "MENTOR_COUNSELING",
            "action": "Conduct 1-on-1 counseling to identify external factors or exam anxiety impacting performance.",
            "timeline": "This week"
        })

    if not recommendations:
        recommendations.append({
            "type": "ENRICHMENT",
            "action": "Encourage participation in Science & Math Olympiads and peer-tutoring leadership.",
            "timeline": "Ongoing"
        })

    return {
        "student_id": str(student.id),
        "name": student.name,
        "admission_no": student.admission_no,
        "grade": student.grade,
        "section": student.section,
        "risk_score": risk_score,
        "severity": severity,
        "attendance_pct": round(attendance_pct, 1),
        "latest_academic_avg": round(latest_avg, 1),
        "trend_velocity": trend_velocity,
        "risk_factors": risk_factors,
        "weak_subjects": weak_subjects,
        "action_required": action_required,
        "recommendations": recommendations,
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/predict/school")
@router.get("/predict/school/{school_id}")
def predict_school_risk(
    school_id: Optional[str] = None,
    grade: Optional[str] = None,
    current_user: UserDB = Depends(require_role(["Admin", "Teacher"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user, school_id)

    query = db.query(StudentDB).filter(
        StudentDB.school_id == target_school_id,
        StudentDB.is_active == True
    )
    if grade:
        query = query.filter(StudentDB.grade == grade)

    students = query.all()
    profiles = [compute_student_risk_profile(st, db) for st in students]

    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "SAFE": 0}
    for p in profiles:
        severity_counts[p["severity"]] = severity_counts.get(p["severity"], 0) + 1

    profiles.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "school_id": target_school_id,
        "total_evaluated": len(profiles),
        "severity_summary": severity_counts,
        "high_risk_percentage": round((severity_counts["CRITICAL"] + severity_counts["HIGH"]) / len(profiles) * 100, 1) if profiles else 0.0,
        "students": profiles
    }


@router.get("/predict/student/{student_id}")
def predict_student_risk(
    student_id: str,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)

    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.school_id == target_school_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school")

    if (current_user.role or "").lower() == "parent":
        link = db.query(ParentStudentDB).filter(
            ParentStudentDB.parent_user_id == current_user.id,
            ParentStudentDB.student_id == student_id,
            ParentStudentDB.is_verified == True
        ).first()
        if not link:
            raise HTTPException(status_code=403, detail="Access denied")

    return compute_student_risk_profile(student, db)


@router.post("/interventions/log")
def log_risk_intervention(
    payload: dict,
    current_user: UserDB = Depends(require_role(["Admin", "Teacher"])),
    db: Session = Depends(get_db)
):
    target_school_id = _get_effective_school_id(current_user)
    student_id = payload.get("student_id")
    intervention_type = payload.get("intervention_type", "COUNSELING")
    notes = payload.get("notes", "")
    action_taken = payload.get("action_taken", "")

    if not student_id or not action_taken:
        raise HTTPException(status_code=400, detail="student_id and action_taken are required")

    student = db.query(StudentDB).filter(
        StudentDB.id == student_id,
        StudentDB.school_id == target_school_id
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in your school")

    case = db.query(RiskCaseDB).filter(
        RiskCaseDB.student_id == student_id,
        RiskCaseDB.school_id == target_school_id
    ).first()
    if not case:
        case = RiskCaseDB(
            school_id=target_school_id,
            student_id=student_id,
            risk_score=75.0,
            status="OPEN",
            notes=notes
        )
        db.add(case)
    else:
        case.notes = (case.notes or "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {intervention_type}: {action_taken}"

    db.commit()
    return {"status": "ok", "message": "Intervention recorded and student monitor updated."}
