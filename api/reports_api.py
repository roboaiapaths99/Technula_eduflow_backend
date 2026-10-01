"""
Reports API — Enterprise administrative reports and data export endpoints.
Provides monthly attendance, fee collection summaries, and student strength breakdowns.
Supports both JSON responses and direct CSV downloads.
"""
from __future__ import annotations
import csv
import io
from datetime import date, datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from db.session import get_db
from models.student_db import StudentDB
from models.attendance_db import AttendanceDB
from models.fee_payment_db import FeePaymentDB
from models.fee_structure_db import FeeStructureDB
from models.user_db import UserDB
from auth.dependencies import require_role, get_current_user

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/attendance-monthly")
def get_monthly_attendance_report(
    year: int = Query(default=lambda: datetime.now(timezone.utc).year),
    month: int = Query(default=lambda: datetime.now(timezone.utc).month, ge=1, le=12),
    grade: Optional[str] = Query(None),
    section: Optional[str] = Query(None),
    format: str = Query("json", description="json or csv"),
    user: UserDB = Depends(require_role(["Admin", "Principal", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """Monthly attendance aggregate and student breakdown."""
    school_id = user.school_id

    st_query = db.query(StudentDB).filter(StudentDB.school_id == school_id, StudentDB.is_active == True)
    if grade:
        st_query = st_query.filter(StudentDB.grade == grade)
    if section:
        st_query = st_query.filter(StudentDB.section == section)

    students = st_query.order_by(StudentDB.grade.asc(), StudentDB.section.asc(), StudentDB.roll_no.asc()).all()
    student_ids = [s.id for s in students]

    # Attendance records in that month
    att_records = (
        db.query(AttendanceDB)
        .filter(
            AttendanceDB.school_id == school_id,
            AttendanceDB.student_id.in_(student_ids),
            extract("year", AttendanceDB.date) == year,
            extract("month", AttendanceDB.date) == month,
        )
        .all()
    )

    stats_by_student = {}
    for r in att_records:
        sid = str(r.student_id)
        if sid not in stats_by_student:
            stats_by_student[sid] = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "total": 0}
        stats_by_student[sid]["total"] += 1
        st_lower = (r.status or "").lower()
        if "present" in st_lower:
            stats_by_student[sid]["present"] += 1
        elif "absent" in st_lower:
            stats_by_student[sid]["absent"] += 1
        elif "late" in st_lower:
            stats_by_student[sid]["late"] += 1
        elif "half" in st_lower:
            stats_by_student[sid]["half_day"] += 1

    report_rows = []
    for s in students:
        sid = str(s.id)
        stat = stats_by_student.get(sid, {"present": 0, "absent": 0, "late": 0, "half_day": 0, "total": 0})
        pct = round((stat["present"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0.0
        report_rows.append({
            "student_id": sid,
            "name": s.name,
            "admission_no": s.admission_no,
            "grade": s.grade,
            "section": s.section,
            "roll_no": s.roll_no or "-",
            "days_present": stat["present"],
            "days_absent": stat["absent"],
            "days_late": stat["late"],
            "total_marked": stat["total"],
            "attendance_rate": pct,
        })

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Admission No", "Student Name", "Grade", "Section", "Roll No", "Present", "Absent", "Late", "Total Days", "Attendance Rate %"])
        for r in report_rows:
            writer.writerow([r["admission_no"], r["name"], r["grade"], r["section"], r["roll_no"], r["days_present"], r["days_absent"], r["days_late"], r["total_marked"], r["attendance_rate"]])
        csv_data = output.getvalue()
        return Response(content=csv_data, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=attendance_{year}_{month:02d}.csv"})

    return {
        "year": year,
        "month": month,
        "total_students": len(students),
        "report": report_rows,
    }


@router.get("/fee-collection")
def get_fee_collection_report(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    payment_mode: Optional[str] = Query(None),
    format: str = Query("json", description="json or csv"),
    user: UserDB = Depends(require_role(["Admin", "Accountant"])),
    db: Session = Depends(get_db),
):
    """Summary and itemized report of fee transactions."""
    school_id = user.school_id
    query = db.query(FeePaymentDB).filter(
        FeePaymentDB.school_id == school_id,
        FeePaymentDB.gateway_status == "COMPLETED"
    )

    if start_date:
        query = query.filter(FeePaymentDB.payment_date >= start_date)
    if end_date:
        query = query.filter(FeePaymentDB.payment_date <= end_date)
    if payment_mode:
        query = query.filter(FeePaymentDB.payment_mode == payment_mode)

    payments = query.order_by(FeePaymentDB.payment_date.desc()).all()

    total_amount = sum(p.total_paid for p in payments)
    mode_breakdown = {}
    for p in payments:
        mode_breakdown[p.payment_mode] = mode_breakdown.get(p.payment_mode, 0.0) + p.total_paid

    items = []
    for p in payments:
        st = p.student
        items.append({
            "receipt_no": p.receipt_no,
            "student_name": st.name if st else "Unknown",
            "admission_no": st.admission_no if st else "Unknown",
            "grade": st.grade if st else "-",
            "section": st.section if st else "-",
            "total_paid": p.total_paid,
            "payment_mode": p.payment_mode,
            "transaction_ref": p.transaction_ref or "-",
            "payment_date": p.payment_date.isoformat(),
        })

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Receipt No", "Student Name", "Admission No", "Grade", "Section", "Amount Paid", "Payment Mode", "Ref / UTR", "Date"])
        for it in items:
            writer.writerow([it["receipt_no"], it["student_name"], it["admission_no"], it["grade"], it["section"], it["total_paid"], it["payment_mode"], it["transaction_ref"], it["payment_date"]])
        csv_data = output.getvalue()
        return Response(content=csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=fee_collection_report.csv"})

    return {
        "total_collected": total_amount,
        "transaction_count": len(payments),
        "mode_breakdown": mode_breakdown,
        "items": items,
    }


@router.get("/student-strength")
def get_student_strength_report(
    format: str = Query("json", description="json or csv"),
    user: UserDB = Depends(require_role(["Admin", "Principal"])),
    db: Session = Depends(get_db),
):
    """Class-by-class student strength breakdown by gender and total."""
    school_id = user.school_id
    rows = (
        db.query(
            StudentDB.grade,
            StudentDB.section,
            func.count(StudentDB.id).label("total"),
            func.sum(func.case((StudentDB.gender.in_(["Male", "male", "M"]), 1), else_=0)).label("boys"),
            func.sum(func.case((StudentDB.gender.in_(["Female", "female", "F"]), 1), else_=0)).label("girls"),
        )
        .filter(StudentDB.school_id == school_id, StudentDB.is_active == True)
        .group_by(StudentDB.grade, StudentDB.section)
        .order_by(StudentDB.grade.asc(), StudentDB.section.asc())
        .all()
    )

    items = []
    grand_total = 0
    grand_boys = 0
    grand_girls = 0
    for r in rows:
        t = r.total or 0
        b = int(r.boys or 0)
        g = int(r.girls or 0)
        grand_total += t
        grand_boys += b
        grand_girls += g
        items.append({
            "grade": r.grade,
            "section": r.section,
            "boys": b,
            "girls": g,
            "other": t - (b + g),
            "total": t,
        })

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Grade", "Section", "Boys", "Girls", "Other", "Total"])
        for it in items:
            writer.writerow([it["grade"], it["section"], it["boys"], it["girls"], it["other"], it["total"]])
        writer.writerow(["TOTAL", "-", grand_boys, grand_girls, grand_total - (grand_boys + grand_girls), grand_total])
        csv_data = output.getvalue()
        return Response(content=csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=student_strength_report.csv"})

    return {
        "grand_total": grand_total,
        "grand_boys": grand_boys,
        "grand_girls": grand_girls,
        "breakdown": items,
    }
