"""
SuperAdmin API — Platform owner (SaaS) management endpoints.
Accessible only by users with role 'SuperAdmin'.
Handles: School listing, suspension, activation, impersonation, audit logs, dashboard stats.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models.school import SchoolDB
from models.user_db import UserDB
from models.student_db import StudentDB
from models.audit_log_db import AuditLogDB
from auth.dependencies import require_super_admin, get_current_user
from auth.auth_service import create_access_token

router = APIRouter(prefix="/superadmin", tags=["SuperAdmin"])


# ── Dashboard Stats ──────────────────────────────────
@router.get("/dashboard")
@router.get("/stats")
def superadmin_dashboard(
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Platform-wide KPIs for the SaaS owner."""
    total_schools = db.query(func.count(SchoolDB.id)).filter(SchoolDB.is_active == True).scalar() or 0
    total_students = db.query(func.count(StudentDB.id)).filter(StudentDB.is_active == True).scalar() or 0
    total_teachers = db.query(func.count(UserDB.id)).filter(
        UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]),
        UserDB.is_active == True,
    ).scalar() or 0
    total_parents = db.query(func.count(UserDB.id)).filter(
        UserDB.role == "Parent",
        UserDB.is_active == True,
    ).scalar() or 0
    suspended_schools = db.query(func.count(SchoolDB.id)).filter(SchoolDB.is_suspended == True).scalar() or 0

    return {
        "total_schools": total_schools,
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_parents": total_parents,
        "suspended_schools": suspended_schools,
        "active_schools": total_schools - suspended_schools,
    }


# ── List All Schools ─────────────────────────────────
@router.get("/schools")
def list_all_schools(
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """List all registered schools with stats and optional pagination."""
    query = db.query(SchoolDB)

    if status == "active":
        query = query.filter(SchoolDB.is_active == True, SchoolDB.is_suspended == False)
    elif status == "suspended":
        query = query.filter(SchoolDB.is_suspended == True)
    elif status == "inactive":
        query = query.filter(SchoolDB.is_active == False)

    if search:
        term = search.strip().lower()
        query = query.filter(
            (SchoolDB.name.ilike(f"%{term}%")) | (SchoolDB.city.ilike(f"%{term}%"))
        )

    total = query.count()
    if page is not None:
        eff_limit = limit or 20
        offset = (page - 1) * eff_limit
        schools = query.order_by(SchoolDB.created_at.desc()).offset(offset).limit(eff_limit).all()
    else:
        schools = query.order_by(SchoolDB.created_at.desc()).all()

    results = []
    for s in schools:
        student_count = db.query(func.count(StudentDB.id)).filter(
            StudentDB.school_id == s.id,
            StudentDB.is_active == True,
        ).scalar() or 0
        teacher_count = db.query(func.count(UserDB.id)).filter(
            UserDB.school_id == s.id,
            UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]),
            UserDB.is_active == True,
        ).scalar() or 0
        parent_count = db.query(func.count(UserDB.id)).filter(
            UserDB.school_id == s.id,
            UserDB.role == "Parent",
            UserDB.is_active == True,
        ).scalar() or 0

        results.append({
            "id": str(s.id),
            "name": s.name,
            "board": s.board,
            "city": s.city,
            "state": s.state,
            "email": s.email,
            "phone": s.phone,
            "logo_url": s.logo_url,
            "is_active": s.is_active,
            "is_suspended": s.is_suspended,
            "max_students": s.max_students,
            "max_teachers": s.max_teachers,
            "student_count": student_count,
            "teacher_count": teacher_count,
            "parent_count": parent_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    if page is not None:
        eff_limit = limit or 20
        return {
            "items": results,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    return results


# ── Get School Detail ────────────────────────────────
@router.get("/schools/{school_id}")
def get_school_detail(
    school_id: str,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Get detailed school info + usage stats."""
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    student_count = db.query(func.count(StudentDB.id)).filter(
        StudentDB.school_id == school.id, StudentDB.is_active == True
    ).scalar() or 0
    teacher_count = db.query(func.count(UserDB.id)).filter(
        UserDB.school_id == school.id,
        UserDB.role.in_(["Teacher", "ClassTeacher", "SubjectTeacher"]),
        UserDB.is_active == True,
    ).scalar() or 0
    parent_count = db.query(func.count(UserDB.id)).filter(
        UserDB.school_id == school.id, UserDB.role == "Parent", UserDB.is_active == True
    ).scalar() or 0

    # Get admin user
    admin = db.query(UserDB).filter(
        UserDB.school_id == school.id, UserDB.role == "Admin"
    ).first()

    return {
        "id": str(school.id),
        "name": school.name,
        "board": school.board,
        "affiliation_no": school.affiliation_no,
        "principal_name": school.principal_name,
        "website": school.website,
        "academic_year": school.academic_year,
        "address": school.address,
        "city": school.city,
        "state": school.state,
        "phone": school.phone,
        "email": school.email,
        "logo_url": school.logo_url,
        "is_active": school.is_active,
        "is_suspended": school.is_suspended,
        "max_students": school.max_students,
        "max_teachers": school.max_teachers,
        "student_count": student_count,
        "teacher_count": teacher_count,
        "parent_count": parent_count,
        "admin_name": admin.full_name if admin else None,
        "admin_email": admin.email if admin else None,
        "created_at": school.created_at.isoformat() if school.created_at else None,
    }


# ── Suspend School ───────────────────────────────────
@router.post("/schools/{school_id}/suspend")
def suspend_school(
    school_id: str,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Suspend a school — blocks all logins for that school."""
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    school.is_suspended = True
    db.commit()

    # Log audit
    audit = AuditLogDB(
        school_id=school.id,
        user_id=user.id,
        user_email=user.email,
        action="school.suspend",
        resource_type="school",
        resource_id=str(school.id),
        details={"school_name": school.name},
    )
    db.add(audit)
    db.commit()

    return {"status": "ok", "message": f"School '{school.name}' has been suspended"}


# ── Activate School ──────────────────────────────────
@router.post("/schools/{school_id}/activate")
def activate_school(
    school_id: str,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Re-activate a suspended school."""
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    school.is_suspended = False
    school.is_active = True
    db.commit()

    audit = AuditLogDB(
        school_id=school.id,
        user_id=user.id,
        user_email=user.email,
        action="school.activate",
        resource_type="school",
        resource_id=str(school.id),
        details={"school_name": school.name},
    )
    db.add(audit)
    db.commit()

    return {"status": "ok", "message": f"School '{school.name}' has been re-activated"}


# ── Update School Details, Limits & Subscription Plan ────────
@router.put("/schools/{school_id}")
def update_school_detail_and_plan(
    school_id: str,
    payload: dict,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """
    SuperAdmin: Update school metadata, quota limits, and subscription plan.
    Synchronizes SchoolDB and SubscriptionPlanDB records.
    """
    from models.subscription_plan_db import (
        SubscriptionPlanDB,
        PLAN_FEATURES,
        PLAN_QUOTAS,
        PLAN_PRICING,
    )

    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    # Update basic profile
    if "name" in payload and payload["name"]:
        school.name = payload["name"].strip()
    if "board" in payload and payload["board"]:
        school.board = payload["board"].strip()
    if "city" in payload:
        school.city = (payload["city"] or "").strip()
    if "state" in payload:
        school.state = (payload["state"] or "").strip()
    if "phone" in payload:
        school.phone = (payload["phone"] or "").strip()

    # Update student & staff quotas
    if "max_students" in payload and payload["max_students"] is not None:
        school.max_students = int(payload["max_students"])
    if "max_teachers" in payload and payload["max_teachers"] is not None:
        school.max_teachers = int(payload["max_teachers"])

    # Update Subscription Plan if provided
    plan_updated = False
    if "subscription_plan" in payload and payload["subscription_plan"]:
        tier = str(payload["subscription_plan"]).lower().strip()
        if tier in ["starter", "growth", "enterprise"]:
            school.subscription_plan = tier
            sub = db.query(SubscriptionPlanDB).filter(SubscriptionPlanDB.school_id == school.id).first()
            now = datetime.now(timezone.utc)
            max_students = school.max_students or PLAN_QUOTAS[tier]["max_students"]
            max_staff = school.max_teachers or PLAN_QUOTAS[tier]["max_staff"]
            features = PLAN_FEATURES[tier]

            if not sub:
                sub = SubscriptionPlanDB(
                    school_id=school.id,
                    plan_tier=tier,
                    billing_cycle="monthly",
                    amount=0 if tier == "starter" else PLAN_PRICING[tier]["monthly"],
                    max_students=max_students,
                    max_staff=max_staff,
                    features=features,
                    is_active=True,
                    is_trial=(tier == "starter"),
                    started_at=now,
                    expires_at=now + timedelta(days=365 if tier != "starter" else 30),
                )
                db.add(sub)
            else:
                sub.plan_tier = tier
                sub.max_students = max_students
                sub.max_staff = max_staff
                sub.features = features
                sub.is_active = True
                if tier != "starter":
                    sub.is_trial = False
            plan_updated = True

    db.commit()
    db.refresh(school)

    # Audit log
    audit = AuditLogDB(
        school_id=school.id,
        user_id=user.id,
        user_email=user.email,
        action="school.update",
        resource_type="school",
        resource_id=str(school.id),
        details={"updated_fields": list(payload.keys()), "plan_updated": plan_updated},
    )
    db.add(audit)
    db.commit()

    return {
        "status": "ok",
        "message": f"School '{school.name}' updated successfully",
        "school": {
            "id": str(school.id),
            "name": school.name,
            "subscription_plan": school.subscription_plan,
            "max_students": school.max_students,
            "max_teachers": school.max_teachers,
        }
    }


# ── Update School Limits ─────────────────────────────
@router.put("/schools/{school_id}/limits")
def update_school_limits(
    school_id: str,
    payload: dict,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Update max students/teachers limits for a school."""
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    if "max_students" in payload:
        school.max_students = int(payload["max_students"])
    if "max_teachers" in payload:
        school.max_teachers = int(payload["max_teachers"])

    db.commit()
    return {"status": "ok", "message": f"Limits updated for '{school.name}'"}


# ── Impersonate School Admin ─────────────────────────
@router.post("/schools/{school_id}/impersonate")
def impersonate_school_admin(
    school_id: str,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """
    Generate a temporary access token as the school's admin.
    Used for support/debugging — login as the school admin.
    """
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    admin = db.query(UserDB).filter(
        UserDB.school_id == school_id,
        UserDB.role == "Admin",
        UserDB.is_active == True,
    ).first()

    if not admin:
        raise HTTPException(status_code=404, detail="No active admin found for this school")

    token = create_access_token({
        "sub": str(admin.id),
        "role": admin.role,
        "school_id": str(admin.school_id),
        "impersonated_by": str(user.id),
    }, expires_minutes=60)  # 1 hour max

    # Audit log
    audit = AuditLogDB(
        school_id=school_id,
        user_id=user.id,
        user_email=user.email,
        action="school.impersonate",
        resource_type="user",
        resource_id=str(admin.id),
        details={"admin_email": admin.email, "admin_name": admin.full_name},
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "impersonated_user": {
            "id": str(admin.id),
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role,
            "school_id": str(admin.school_id),
        },
        "school": {
            "id": str(school.id),
            "name": school.name,
            "code": school.code,
        },
        "expires_in_minutes": 60,
    }


# ── Delete School ────────────────────────────────────
@router.delete("/schools/{school_id}")
def delete_school(
    school_id: str,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Permanently delete a school and all its data. USE WITH CAUTION."""
    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    school_name = school.name

    # Audit before deletion
    audit = AuditLogDB(
        user_id=user.id,
        user_email=user.email,
        action="school.delete",
        resource_type="school",
        resource_id=str(school.id),
        details={"school_name": school_name, "school_email": school.email},
    )
    db.add(audit)

    db.delete(school)  # CASCADE will remove all related data
    db.commit()

    return {"status": "ok", "message": f"School '{school_name}' and all its data has been permanently deleted"}


# ── Audit Logs ───────────────────────────────────────
@router.get("/audit-logs")
def list_audit_logs(
    school_id: Optional[str] = None,
    action: Optional[str] = None,
    page: Optional[int] = None,
    limit: int = 50,
    user=Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """Cross-school audit trail with pagination."""
    query = db.query(AuditLogDB)
    if school_id:
        query = query.filter(AuditLogDB.school_id == school_id)
    if action:
        query = query.filter(AuditLogDB.action.ilike(f"%{action}%"))

    total = query.count()
    if page is not None:
        eff_limit = limit or 50
        offset = (page - 1) * eff_limit
        logs = query.order_by(AuditLogDB.created_at.desc()).offset(offset).limit(eff_limit).all()
    else:
        logs = query.order_by(AuditLogDB.created_at.desc()).limit(limit).all()

    items = [
        {
            "id": str(l.id),
            "school_id": str(l.school_id) if l.school_id else None,
            "user_id": str(l.user_id) if l.user_id else None,
            "user_email": l.user_email,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "details": l.details,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]

    if page is not None:
        eff_limit = limit or 50
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": eff_limit,
            "total_pages": (total + eff_limit - 1) // eff_limit,
        }

    return items
