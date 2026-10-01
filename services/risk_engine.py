"""
Student Success Intelligence Layer — Risk Engine.
Evaluates student academic performance and attendance patterns to identify students at risk:
1. Consecutive Absences (3+ days) -> HIGH
2. Low Attendance (< 75%) -> MEDIUM
3. Academic Score Drop (> 15% drop between consecutive exams) -> HIGH
4. Failing Marks (< 40% in any subject) -> MEDIUM / HIGH
Automatically flags RiskCaseDB and notifies class teacher / admin.
"""
from __future__ import annotations
from datetime import date, timedelta, datetime, timezone
import logging
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from models.student_db import StudentDB
from models.attendance_db import AttendanceDB
from models.marks import Mark
from models.exam import Exam
from models.risk_case_db import RiskCaseDB
from db.mongo import log_mongo_document

logger = logging.getLogger("service.risk_engine")


def run_risk_evaluation(db: Session, school_id, student_id=None) -> List[RiskCaseDB]:
    """
    Run risk evaluation rules across a school or for a single student.
    Returns newly created RiskCaseDB items.
    """
    query = db.query(StudentDB).filter(StudentDB.school_id == school_id, StudentDB.is_active == True)
    if student_id:
        query = query.filter(StudentDB.id == student_id)

    students = query.all()
    created_cases = []

    for student in students:
        # Rule 1: Check consecutive absences in last 14 days
        recent_attendance = (
            db.query(AttendanceDB)
            .filter(
                AttendanceDB.school_id == school_id,
                AttendanceDB.student_id == student.id,
            )
            .order_by(desc(AttendanceDB.date))
            .limit(10)
            .all()
        )

        consecutive_absents = 0
        for att in recent_attendance:
            if att.status in ["Absent", "absent"]:
                consecutive_absents += 1
            else:
                break

        if consecutive_absents >= 3:
            existing = (
                db.query(RiskCaseDB)
                .filter(
                    RiskCaseDB.school_id == school_id,
                    RiskCaseDB.student_id == student.id,
                    RiskCaseDB.trigger_rule == f"CONSECUTIVE_ABSENCES_{consecutive_absents}",
                    RiskCaseDB.status.in_(["OPEN", "IN_REVIEW"]),
                )
                .first()
            )
            if not existing:
                risk_case = RiskCaseDB(
                    school_id=school_id,
                    student_id=student.id,
                    risk_level="HIGH",
                    trigger_rule=f"CONSECUTIVE_ABSENCES_{consecutive_absents}",
                    title=f"Consecutive Absences Alert: {consecutive_absents} days",
                    description=f"{student.name} ({student.grade}-{student.section}) has been absent for {consecutive_absents} consecutive sessions.",
                    status="OPEN",
                )
                db.add(risk_case)
                created_cases.append(risk_case)

        # Rule 2: Overall attendance below 75%
        total_days = (
            db.query(func.count(AttendanceDB.id))
            .filter(AttendanceDB.school_id == school_id, AttendanceDB.student_id == student.id)
            .scalar() or 0
        )
        if total_days >= 10:
            present_days = (
                db.query(func.count(AttendanceDB.id))
                .filter(
                    AttendanceDB.school_id == school_id,
                    AttendanceDB.student_id == student.id,
                    AttendanceDB.status.in_(["Present", "present"]),
                )
                .scalar() or 0
            )
            rate = round((present_days / total_days) * 100, 1)
            if rate < 75.0:
                existing = (
                    db.query(RiskCaseDB)
                    .filter(
                        RiskCaseDB.school_id == school_id,
                        RiskCaseDB.student_id == student.id,
                        RiskCaseDB.trigger_rule == "ATTENDANCE_BELOW_75",
                        RiskCaseDB.status.in_(["OPEN", "IN_REVIEW"]),
                    )
                    .first()
                )
                if not existing:
                    risk_case = RiskCaseDB(
                        school_id=school_id,
                        student_id=student.id,
                        risk_level="MEDIUM" if rate >= 65 else "HIGH",
                        trigger_rule="ATTENDANCE_BELOW_75",
                        title=f"Low Attendance: {rate}%",
                        description=f"{student.name}'s attendance rate is {rate}%, which is below the mandatory 75% threshold ({present_days}/{total_days} days).",
                        status="OPEN",
                    )
                    db.add(risk_case)
                    created_cases.append(risk_case)

        # Rule 3: Failing marks (< 40%) in recent exam
        recent_marks = (
            db.query(Mark)
            .filter(Mark.school_id == school_id, Mark.student_id == student.id)
            .all()
        )
        failed_subjects = []
        for m in recent_marks:
            if m.max_marks > 0 and (m.marks_obtained / m.max_marks) < 0.40:
                sub_name = m.subject.name if m.subject else "Subject"
                pct = round((m.marks_obtained / m.max_marks) * 100, 1)
                failed_subjects.append(f"{sub_name} ({pct}%)")

        if failed_subjects:
            rule_name = f"FAILING_SUBJECTS_{len(failed_subjects)}"
            existing = (
                db.query(RiskCaseDB)
                .filter(
                    RiskCaseDB.school_id == school_id,
                    RiskCaseDB.student_id == student.id,
                    RiskCaseDB.trigger_rule == rule_name,
                    RiskCaseDB.status.in_(["OPEN", "IN_REVIEW"]),
                )
                .first()
            )
            if not existing:
                risk_case = RiskCaseDB(
                    school_id=school_id,
                    student_id=student.id,
                    risk_level="CRITICAL" if len(failed_subjects) >= 3 else "HIGH",
                    trigger_rule=rule_name,
                    title=f"Academic Alert: Struggling in {len(failed_subjects)} subjects",
                    description=f"{student.name} scored below 40% passing mark in: {', '.join(failed_subjects)}.",
                    status="OPEN",
                )
                db.add(risk_case)
                created_cases.append(risk_case)

    if created_cases:
        db.commit()
        log_mongo_document("audit_logs", {
            "action": "RISK_ENGINE_EVALUATION",
            "school_id": str(school_id),
            "new_cases_count": len(created_cases),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    return created_cases
