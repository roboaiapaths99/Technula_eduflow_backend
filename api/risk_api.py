"""
Student Success Intelligence Layer — Risk API.
SECURED: All school_id values come from JWT user context, never from client.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.session import get_db
from models.risk_case_db import RiskCaseDB
from models.student_db import StudentDB
from services.risk_engine import run_risk_evaluation
from auth.dependencies import require_role

router = APIRouter(prefix="/risk-cases", tags=["Risk Cases"])


class ResolveRiskRequest(BaseModel):
    status: str  # IN_REVIEW, ACTION_TAKEN, RESOLVED
    resolution_notes: str
    assigned_to: Optional[str] = None


@router.get("/")
def list_risk_cases(
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    grade: Optional[str] = None,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """List risk cases with filters for status, level, grade."""
    school_id = str(user.school_id)

    query = (
        db.query(RiskCaseDB, StudentDB)
        .join(StudentDB, RiskCaseDB.student_id == StudentDB.id)
        .filter(RiskCaseDB.school_id == school_id)
    )

    if status:
        query = query.filter(RiskCaseDB.status == status)
    if risk_level:
        query = query.filter(RiskCaseDB.risk_level == risk_level)
    if grade:
        query = query.filter(StudentDB.grade == grade)

    cases = query.order_by(RiskCaseDB.created_at.desc()).all()

    result = []
    for rc, s in cases:
        result.append({
            "id": str(rc.id),
            "school_id": str(rc.school_id),
            "student_id": str(s.id),
            "student_name": s.name,
            "admission_no": s.admission_no,
            "grade": s.grade,
            "section": s.section,
            "risk_level": rc.risk_level,
            "trigger_rule": rc.trigger_rule,
            "title": rc.title,
            "description": rc.description,
            "status": rc.status,
            "resolution_notes": rc.resolution_notes,
            "created_at": rc.created_at.isoformat() if rc.created_at else None,
            "resolved_at": rc.resolved_at.isoformat() if rc.resolved_at else None,
        })

    return result


@router.post("/scan")
def trigger_school_scan(
    user=Depends(require_role(["Admin"])),
    db: Session = Depends(get_db),
):
    """Manually trigger risk engine scan across the school."""
    school_id = str(user.school_id)
    new_cases = run_risk_evaluation(db, school_id=school_id)
    return {
        "status": "success",
        "school_id": school_id,
        "new_cases_created": len(new_cases),
        "message": f"Risk scan completed. {len(new_cases)} new risk cases identified.",
    }


@router.patch("/{case_id}")
def update_risk_case(
    case_id: str,
    req: ResolveRiskRequest,
    user=Depends(require_role(["Admin", "Teacher", "ClassTeacher"])),
    db: Session = Depends(get_db),
):
    """Update risk case status, notes, or mark resolved."""
    case = db.query(RiskCaseDB).filter(RiskCaseDB.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Risk case not found")

    if user.role != "SuperAdmin" and str(case.school_id) != str(user.school_id):
        raise HTTPException(status_code=403, detail="Access denied")

    case.status = req.status
    case.resolution_notes = req.resolution_notes
    if req.assigned_to:
        case.assigned_to = req.assigned_to
    if req.status == "RESOLVED":
        case.resolved_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "success", "message": "Risk case updated successfully"}
