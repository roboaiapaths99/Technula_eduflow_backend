"""
Admin Command Center Dashboard Statistics API.
Provides executive-level metrics and health indicators for school administration.
SECURED: All endpoints require auth and derive school_id from the JWT user context.
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models.student_db import StudentDB
from models.user_db import UserDB
from models.attendance_db import AttendanceDB
from models.risk_case_db import RiskCaseDB
from models.ticket_db import TicketDB
from models.exam import Exam
from models.school import SchoolDB
from models.fee_payment_db import FeePaymentDB
from models.fee_structure_db import FeeStructureDB
from services.gemini_service import generate_weekly_executive_summary
from auth.dependencies import get_current_user, require_role

router = APIRouter(prefix="/admin-stats", tags=["Admin Statistics"])


def _get_effective_school_id(user: UserDB, school_id_override: Optional[str] = None) -> str:
    if (user.role or "").strip() == "SuperAdmin" and school_id_override:
        return school_id_override
    if not user.school_id:
        raise HTTPException(status_code=403, detail="User is not assigned to any school")
    return str(user.school_id)


@router.get("/overview")
def get_admin_overview(
    school_id: Optional[str] = None,
    current_user: UserDB = Depends(require_role(["Admin", "Teacher"])),
    db: Session = Depends(get_db)
):
    """Summary KPI metrics for Admin Command Center."""
    target_school_id = _get_effective_school_id(current_user, school_id)
    today = date.today()

    total_students = (
        db.query(func.count(StudentDB.id))
        .filter(StudentDB.school_id == target_school_id, StudentDB.is_active == True)
        .scalar() or 0
    )

    total_teachers = (
        db.query(func.count(UserDB.id))
        .filter(
            UserDB.school_id == target_school_id,
            UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]),
            UserDB.is_active == True,
        )
        .scalar() or 0
    )

    total_parents = (
        db.query(func.count(UserDB.id))
        .filter(UserDB.school_id == target_school_id, UserDB.role == "Parent", UserDB.is_active == True)
        .scalar() or 0
    )

    # Today's attendance
    today_total = (
        db.query(func.count(AttendanceDB.id))
        .filter(AttendanceDB.school_id == target_school_id, AttendanceDB.date == today)
        .scalar() or 0
    )
    today_present = (
        db.query(func.count(AttendanceDB.id))
        .filter(
            AttendanceDB.school_id == target_school_id,
            AttendanceDB.date == today,
            AttendanceDB.status.in_(["Present", "present"]),
        )
        .scalar() or 0
    )
    att_rate = round((today_present / today_total * 100), 1) if today_total > 0 else 0.0

    # Risk cases breakdown
    open_risks = (
        db.query(RiskCaseDB)
        .filter(RiskCaseDB.school_id == target_school_id, RiskCaseDB.status.in_(["OPEN", "IN_REVIEW"]))
        .all()
    )
    critical_risks = sum(1 for r in open_risks if r.risk_level == "CRITICAL")
    high_risks = sum(1 for r in open_risks if r.risk_level == "HIGH")
    medium_risks = sum(1 for r in open_risks if r.risk_level == "MEDIUM")

    # Tickets breakdown
    open_tickets = (
        db.query(func.count(TicketDB.id))
        .filter(TicketDB.school_id == target_school_id, TicketDB.status.in_(["OPEN", "IN_PROGRESS"]))
        .scalar() or 0
    )

    # Total exams
    total_exams = (
        db.query(func.count(Exam.id))
        .filter(Exam.school_id == target_school_id)
        .scalar() or 0
    )

    return {
        "kpis": {
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_parents": total_parents,
            "today_attendance_rate": att_rate,
            "today_present_count": today_present,
            "today_marked_count": today_total,
            "active_risk_cases": len(open_risks),
            "critical_risks": critical_risks,
            "high_risks": high_risks,
            "medium_risks": medium_risks,
            "open_tickets": open_tickets,
            "total_exams": total_exams,
        },
        "school_health_score": max(50, round(100 - (critical_risks * 5 + high_risks * 2 + open_tickets * 1.5))),
    }


@router.get("/weekly-report")
def get_weekly_executive_report(
    school_id: Optional[str] = None,
    current_user: UserDB = Depends(require_role(["Admin"])),
    db: Session = Depends(get_db)
):
    """
    Principal's Weekly AI School Health Report.
    Compiles 7-day attendance pulse, financial collections, risk caseload,
    and calls Gemini AI to generate an executive-ready briefing.
    """
    target_school_id = _get_effective_school_id(current_user, school_id)
    school = db.query(SchoolDB).filter(SchoolDB.id == target_school_id).first()
    school_name = school.name if school else "Technula EduFlow"

    today = date.today()
    start_date = today - timedelta(days=6)

    total_students = (
        db.query(func.count(StudentDB.id))
        .filter(StudentDB.school_id == target_school_id, StudentDB.is_active == True)
        .scalar() or 0
    )

    total_teachers = (
        db.query(func.count(UserDB.id))
        .filter(
            UserDB.school_id == target_school_id,
            UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]),
            UserDB.is_active == True,
        )
        .scalar() or 0
    )

    # 7-day attendance pulse
    attendance_pulse = []
    pulse_rates = []
    for i in range(7):
        day_date = start_date + timedelta(days=i)
        tot = (
            db.query(func.count(AttendanceDB.id))
            .filter(AttendanceDB.school_id == target_school_id, AttendanceDB.date == day_date)
            .scalar() or 0
        )
        pres = (
            db.query(func.count(AttendanceDB.id))
            .filter(
                AttendanceDB.school_id == target_school_id,
                AttendanceDB.date == day_date,
                AttendanceDB.status.in_(["Present", "present"]),
            )
            .scalar() or 0
        )
        rate = round((pres / tot * 100), 1) if tot > 0 else 0.0
        pulse_rates.append(rate)
        attendance_pulse.append({
            "date": day_date.isoformat(),
            "day_name": day_date.strftime("%a"),
            "rate": rate,
            "present_count": pres,
            "total_marked": tot,
        })

    avg_att_rate = round(sum(pulse_rates) / len(pulse_rates), 1) if pulse_rates else 0.0

    # Financial collections
    weekly_paid = (
        db.query(func.sum(FeePaymentDB.total_paid))
        .filter(
            FeePaymentDB.school_id == target_school_id,
            FeePaymentDB.payment_date >= start_date,
            FeePaymentDB.gateway_status == "COMPLETED",
        )
        .scalar() or 0.0
    )

    all_structures = (
        db.query(func.sum(FeeStructureDB.total_amount))
        .filter(FeeStructureDB.school_id == target_school_id, FeeStructureDB.is_active == True)
        .scalar() or 0.0
    )
    all_paid = (
        db.query(func.sum(FeePaymentDB.total_paid))
        .filter(FeePaymentDB.school_id == target_school_id, FeePaymentDB.gateway_status == "COMPLETED")
        .scalar() or 0.0
    )
    total_pending = max(0.0, round(float(all_structures) - float(all_paid), 2))

    # Risk cases
    open_risks = (
        db.query(RiskCaseDB)
        .filter(RiskCaseDB.school_id == target_school_id, RiskCaseDB.status.in_(["OPEN", "IN_REVIEW"]))
        .all()
    )
    critical_risks = sum(1 for r in open_risks if r.risk_level == "CRITICAL")
    high_risks = sum(1 for r in open_risks if r.risk_level == "HIGH")
    medium_risks = sum(1 for r in open_risks if r.risk_level == "MEDIUM")

    # Helpdesk tickets
    open_tickets = (
        db.query(func.count(TicketDB.id))
        .filter(TicketDB.school_id == target_school_id, TicketDB.status.in_(["OPEN", "IN_PROGRESS"]))
        .scalar() or 0
    )
    resolved_tickets = (
        db.query(func.count(TicketDB.id))
        .filter(TicketDB.school_id == target_school_id, TicketDB.status == "RESOLVED")
        .scalar() or 0
    )

    kpi_payload = {
        "school_name": school_name,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "attendance_rate": avg_att_rate,
        "critical_risks": critical_risks,
        "high_risks": high_risks,
        "medium_risks": medium_risks,
        "weekly_collected_amount": round(float(weekly_paid), 2),
        "total_pending_amount": total_pending,
        "open_tickets": open_tickets,
        "resolved_tickets": resolved_tickets,
    }

    ai_briefing = generate_weekly_executive_summary(kpi_payload)

    return {
        "status": "success",
        "school": {
            "id": target_school_id,
            "name": school_name,
        },
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
        },
        "kpis": kpi_payload,
        "attendance_pulse": attendance_pulse,
        "ai_briefing": ai_briefing,
        "health_score": max(50, round(100 - (critical_risks * 4 + high_risks * 2 + open_tickets * 1.2))),
    }
