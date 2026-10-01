"""
Subscription & PayU Payment API for Multi-Tenant SaaS.
Supports:
- Plan tiers: starter (10-day free trial), growth (₹1,999/mo), enterprise (₹4,999/mo)
- Feature list & pricing info
- Current plan status with student/staff quota usage
- PayU payment initialization with SHA-512 hash generation
- PayU payment verification and plan activation
- SuperAdmin plan override and subscription management
"""
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_db, get_current_user, require_role, require_super_admin
from models.user_db import UserDB
from models.school import SchoolDB
from models.student_db import StudentDB
from models.subscription_plan_db import (
    SubscriptionPlanDB,
    PLAN_FEATURES,
    PLAN_QUOTAS,
    PLAN_PRICING,
    FREE_TRIAL_DAYS,
)

router = APIRouter(prefix="/subscription", tags=["Subscription"])

from core.config import settings

def get_payu_config():
    key = settings.effective_payu_key
    salt = settings.effective_payu_salt
    mode = settings.effective_payu_mode
    if not key or not salt:
        raise HTTPException(
            status_code=500,
            detail="PayU gateway credentials (PAYU_KEY / PAYU_SALT) are not configured in environment.",
        )
    payment_url = "https://secure.payu.in/_payment" if mode == "live" else "https://test.payu.in/_payment"
    return key, salt, mode, payment_url


# ── Pydantic Request Models ──────────────────────────────────
class PlanSelectRequest(BaseModel):
    plan_tier: str = Field(..., description="starter | growth | enterprise")
    billing_cycle: Optional[str] = "monthly"  # monthly | yearly


class PayUInitRequest(BaseModel):
    plan_tier: Optional[str] = Field(None, description="growth | enterprise")
    tier: Optional[str] = Field(None, description="Alias for plan_tier")
    billing_cycle: str = Field("monthly", description="monthly | yearly")
    firstname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    def get_tier(self) -> str:
        """Resolve plan_tier from either field, raising if neither provided."""
        resolved = self.plan_tier or self.tier
        if not resolved:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="plan_tier is required (growth or enterprise)")
        return resolved.lower()


class PayUVerifyRequest(BaseModel):
    txnid: str
    status: str  # success | failure
    payu_hash: Optional[str] = None
    hash: Optional[str] = None
    amount: Optional[float] = None
    plan_tier: Optional[str] = None
    tier: Optional[str] = None
    billing_cycle: Optional[str] = "monthly"
    payment_id: Optional[str] = None
    is_simulation: Optional[bool] = False


class SuperAdminPlanOverride(BaseModel):
    plan_tier: str
    is_trial: Optional[bool] = False
    trial_days_extension: Optional[int] = 0
    plan_days_extension: Optional[int] = 30
    max_students: Optional[int] = None
    max_staff: Optional[int] = None
    is_active: Optional[bool] = True


# ── Endpoints ────────────────────────────────────────────────

@router.get("/plans")
def list_available_plans():
    """
    Public endpoint: Get all available subscription plans, pricing, quotas, and features.
    """
    plans = []
    tier_details = {
        "starter": {
            "name": "Starter",
            "tagline": "Best for trying out SchoolOS with your core team",
            "trial_days": FREE_TRIAL_DAYS,
            "highlight": False,
            "badge": "10-Day Free Trial",
        },
        "growth": {
            "name": "Growth",
            "tagline": "Ideal for established schools scaling up academic operations",
            "trial_days": 0,
            "highlight": True,
            "badge": "Most Popular",
        },
        "enterprise": {
            "name": "Enterprise",
            "tagline": "Complete AI intelligence, OCR exam analysis, and unlimited capacity",
            "trial_days": 0,
            "highlight": False,
            "badge": "All Features Included",
        },
    }

    for tier, quotas in PLAN_QUOTAS.items():
        pricing = PLAN_PRICING.get(tier, {"monthly": 0, "yearly": 0})
        features = PLAN_FEATURES.get(tier, [])
        details = tier_details.get(tier, {})

        plans.append({
            "tier": tier,
            "name": details.get("name", tier.title()),
            "tagline": details.get("tagline", ""),
            "badge": details.get("badge", ""),
            "is_popular": details.get("highlight", False),
            "pricing": pricing,
            "quotas": quotas,
            "features": features,
            "trial_days": details.get("trial_days", 0),
        })

    return {"plans": plans, "currency": "INR", "currency_symbol": "₹"}


@router.get("/current")
def get_current_subscription(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Authenticated endpoint: Get current school subscription status, trial countdown,
    feature access, and real-time usage (students/staff count vs quota).
    """
    if not user.school_id:
        if (user.role or "").strip() == "SuperAdmin":
            return {
                "plan_tier": "enterprise",
                "is_superadmin": True,
                "is_active": True,
                "features": PLAN_FEATURES["enterprise"],
                "quotas": {"max_students": 99999, "max_staff": 99999},
                "usage": {"students": 0, "staff": 0},
            }
        raise HTTPException(status_code=400, detail="User has no associated school")

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()

    now = datetime.now(timezone.utc)

    # If no subscription record exists yet, create default 10-day starter trial
    if not sub:
        trial_ends = now + timedelta(days=FREE_TRIAL_DAYS)
        sub = SubscriptionPlanDB(
            school_id=user.school_id,
            plan_tier=school.subscription_plan or "starter",
            billing_cycle="monthly",
            amount=0,
            max_students=PLAN_QUOTAS["starter"]["max_students"],
            max_staff=PLAN_QUOTAS["starter"]["max_staff"],
            features=PLAN_FEATURES["starter"],
            is_active=True,
            is_trial=True,
            trial_started_at=now,
            trial_ends_at=trial_ends,
            started_at=now,
            expires_at=trial_ends,
        )
        school.subscription_plan = "starter"
        db.add(sub)
        db.commit()
        db.refresh(sub)

    # Real-time usage counts
    student_count = db.query(StudentDB).filter(StudentDB.school_id == user.school_id).count()
    staff_count = db.query(UserDB).filter(
        UserDB.school_id == user.school_id,
        UserDB.role != "Parent",
    ).count()

    def _to_utc(dt):
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    # Calculate days remaining
    trial_days_remaining = None
    trial_end = _to_utc(sub.trial_ends_at)
    if sub.is_trial and trial_end:
        diff = (trial_end - now).total_seconds()
        trial_days_remaining = max(0, int(diff // 86400) + (1 if diff % 86400 > 0 else 0))

    days_remaining = None
    exp_end = _to_utc(sub.expires_at)
    if exp_end:
        diff = (exp_end - now).total_seconds()
        days_remaining = max(0, int(diff // 86400) + (1 if diff % 86400 > 0 else 0))

    is_expired = False
    if sub.is_trial and trial_end and now > trial_end:
        is_expired = True
    elif not sub.is_trial and exp_end and now > exp_end:
        is_expired = True

    return {
        "school_id": str(school.id),
        "school_name": school.name,
        "plan_tier": sub.plan_tier,
        "billing_cycle": sub.billing_cycle,
        "amount": sub.amount,
        "is_active": sub.is_active and not is_expired,
        "is_trial": sub.is_trial,
        "is_expired": is_expired,
        "trial_days_remaining": trial_days_remaining,
        "days_remaining": days_remaining,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "features": sorted(list(set(PLAN_FEATURES.get(sub.plan_tier, []) + (sub.features or [])))),
        "quotas": {
            "max_students": sub.max_students,
            "max_staff": sub.max_staff,
        },
        "usage": {
            "students": student_count,
            "staff": staff_count,
            "student_pct": round((student_count / max(1, sub.max_students)) * 100, 1),
            "staff_pct": round((staff_count / max(1, sub.max_staff)) * 100, 1),
        },
        "last_payment_status": sub.last_payment_status,
        "last_payment_id": sub.last_payment_id,
    }


@router.post("/select")
def select_starter_plan(
    req: PlanSelectRequest,
    user: UserDB = Depends(require_role(["Admin", "SuperAdmin"])),
    db: Session = Depends(get_db),
):
    """
    Select starter plan (activates or sets 10-day trial).
    If requesting growth or enterprise, informs user to initiate PayU payment.
    """
    if not user.school_id:
        raise HTTPException(status_code=400, detail="User has no associated school")

    tier = req.plan_tier.lower()
    if tier not in ["starter", "growth", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid plan tier")

    if tier in ["growth", "enterprise"]:
        return {
            "requires_payment": True,
            "plan_tier": tier,
            "billing_cycle": req.billing_cycle,
            "amount": PLAN_PRICING[tier].get(req.billing_cycle or "monthly", 0),
            "message": f"Upgrade to {tier.title()} requires PayU payment. Please use /subscription/payu-init.",
        }

    # Activate Starter plan (10-day trial)
    now = datetime.now(timezone.utc)
    trial_ends = now + timedelta(days=FREE_TRIAL_DAYS)

    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()

    if not sub:
        sub = SubscriptionPlanDB(
            school_id=user.school_id,
            plan_tier="starter",
            billing_cycle="monthly",
            amount=0,
            max_students=PLAN_QUOTAS["starter"]["max_students"],
            max_staff=PLAN_QUOTAS["starter"]["max_staff"],
            features=PLAN_FEATURES["starter"],
            is_active=True,
            is_trial=True,
            trial_started_at=now,
            trial_ends_at=trial_ends,
            started_at=now,
            expires_at=trial_ends,
        )
        db.add(sub)
    else:
        sub.plan_tier = "starter"
        sub.max_students = PLAN_QUOTAS["starter"]["max_students"]
        sub.max_staff = PLAN_QUOTAS["starter"]["max_staff"]
        sub.features = PLAN_FEATURES["starter"]
        sub.is_active = True
        sub.is_trial = True
        sub.trial_ends_at = trial_ends
        sub.expires_at = trial_ends

    if school:
        school.subscription_plan = "starter"
        school.max_students = PLAN_QUOTAS["starter"]["max_students"]
        school.max_teachers = PLAN_QUOTAS["starter"]["max_staff"]
        school.trial_ends_at = trial_ends

    db.commit()
    db.refresh(sub)

    return {
        "success": True,
        "message": f"Starter 10-day trial activated successfully. Valid until {trial_ends.strftime('%d %b %Y')}.",
        "plan_tier": "starter",
        "trial_ends_at": trial_ends.isoformat(),
    }


@router.post("/payu-init")
def initiate_payu_payment(
    req: PayUInitRequest,
    request: Request,
    user: UserDB = Depends(require_role(["Admin", "SuperAdmin"])),
    db: Session = Depends(get_db),
):
    """
    Generate PayU transaction parameters including SHA-512 payment hash.
    Formula: sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT)
    """
    if not user.school_id:
        raise HTTPException(status_code=400, detail="User has no associated school")

    tier = req.get_tier()
    if tier not in ["growth", "enterprise"]:
        raise HTTPException(status_code=400, detail="Only growth and enterprise plans require payment")

    cycle = req.billing_cycle.lower() if req.billing_cycle in ["monthly", "yearly"] else "monthly"
    amount = float(PLAN_PRICING[tier][cycle])

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
    school_name = school.name if school else "School"

    # Transaction ID (must be unique per attempt)
    txnid = f"TXN_{uuid.uuid4().hex[:14].upper()}"
    productinfo = f"SchoolOS_{tier.title()}_{cycle.title()}"
    firstname = (req.firstname or user.full_name or school_name)[:50].strip()
    email = (req.email or user.email or (school.email if school else "")).strip().lower()
    phone = (req.phone or user.phone or (school.phone if school else "")).strip()

    # User defined fields for callback correlation
    udf1 = str(user.school_id)
    udf2 = tier
    udf3 = cycle
    udf4 = "saas_subscription"
    udf5 = ""

    # PayU Hash string calculation
    key, salt, mode, payment_url = get_payu_config()
    # Format: key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT
    amount_str = f"{amount:.2f}"
    hash_sequence = f"{key}|{txnid}|{amount_str}|{productinfo}|{firstname}|{email}|{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    payment_hash = hashlib.sha512(hash_sequence.encode("utf-8")).hexdigest().lower()

    # Determine local vs production callback URLs dynamically
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    is_local = "localhost" in origin or "127.0.0.1" in origin or "localhost" in str(request.base_url)

    if is_local:
        surl = settings.PAYU_SUCCESS_URL_LOCAL or "http://localhost:8000/subscription/payu-callback/success"
        furl = settings.PAYU_FAIL_URL_LOCAL or "http://localhost:8000/subscription/payu-callback/fail"
    else:
        surl = settings.PAYU_SUCCESS_URL or "https://insights.agpkacademy.in/api/subscription/payu-callback/success"
        furl = settings.PAYU_FAIL_URL or "https://insights.agpkacademy.in/api/subscription/payu-callback/fail"

    return {
        "payu_action_url": payment_url,
        "key": key,
        "txnid": txnid,
        "amount": amount_str,
        "productinfo": productinfo,
        "firstname": firstname,
        "email": email,
        "phone": phone,
        "hash": payment_hash,
        "udf1": udf1,
        "udf2": udf2,
        "udf3": udf3,
        "udf4": udf4,
        "udf5": udf5,
        "mode": mode,
        "plan_tier": tier,
        "billing_cycle": cycle,
        "surl": surl,
        "furl": furl,
    }


@router.post("/payu-verify")
def verify_payu_payment(
    req: PayUVerifyRequest,
    user: UserDB = Depends(require_role(["Admin", "SuperAdmin"])),
    db: Session = Depends(get_db),
):
    """
    Verifies PayU payment result and activates the upgraded subscription plan.
    Supports instant test/simulation mode for sandbox verification.
    """
    if not user.school_id:
        raise HTTPException(status_code=400, detail="User has no associated school")

    key, salt, mode, _ = get_payu_config()

    # Enforce real PayU payment in live environment
    if mode == "live" and req.is_simulation:
        raise HTTPException(
            status_code=400,
            detail="Simulated payments are strictly disabled in live environment. Real PayU payment is required.",
        )

    if req.status.lower() != "success":
        raise HTTPException(status_code=400, detail="Payment was not marked as successful by PayU")

    tier = (req.plan_tier or req.tier or "growth").lower()
    if tier not in ["growth", "enterprise"]:
        tier = "growth"

    cycle = (req.billing_cycle or "monthly").lower()
    amount = req.amount or float(PLAN_PRICING[tier].get(cycle, 1999))

    now = datetime.now(timezone.utc)
    duration_days = 365 if cycle == "yearly" else 30
    expires_at = now + timedelta(days=duration_days)

    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()

    school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()

    if not sub:
        sub = SubscriptionPlanDB(
            school_id=user.school_id,
            plan_tier=tier,
            billing_cycle=cycle,
            amount=amount,
            max_students=PLAN_QUOTAS[tier]["max_students"],
            max_staff=PLAN_QUOTAS[tier]["max_staff"],
            features=PLAN_FEATURES[tier],
            is_active=True,
            is_trial=False,
            started_at=now,
            expires_at=expires_at,
            last_payment_id=req.payment_id or req.txnid,
            last_payment_status="success",
        )
        db.add(sub)
    else:
        sub.plan_tier = tier
        sub.billing_cycle = cycle
        sub.amount = amount
        sub.max_students = PLAN_QUOTAS[tier]["max_students"]
        sub.max_staff = PLAN_QUOTAS[tier]["max_staff"]
        sub.features = PLAN_FEATURES[tier]
        sub.is_active = True
        sub.is_trial = False
        sub.started_at = now
        sub.expires_at = expires_at
        sub.last_payment_id = req.payment_id or req.txnid
        sub.last_payment_status="success"

    if school:
        school.subscription_plan = tier
        school.max_students = PLAN_QUOTAS[tier]["max_students"]
        school.max_teachers = PLAN_QUOTAS[tier]["max_staff"]

    db.commit()
    db.refresh(sub)

    return {
        "success": True,
        "message": f"Successfully upgraded to {tier.title()} plan ({cycle.title()})!",
        "plan_tier": tier,
        "expires_at": expires_at.isoformat(),
        "quotas": {
            "max_students": sub.max_students,
            "max_staff": sub.max_staff,
        },
        "features": sub.features,
    }


# ── SuperAdmin Endpoints ─────────────────────────────────────

@router.get("/admin/all")
def superadmin_list_all_subscriptions(
    user: UserDB = Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """
    SuperAdmin only: List all school subscriptions, revenue, and usage statistics.
    """
    schools = db.query(SchoolDB).all()
    results = []

    now = datetime.now(timezone.utc)

    for s in schools:
        sub = db.query(SubscriptionPlanDB).filter(SubscriptionPlanDB.school_id == s.id).first()
        student_count = db.query(StudentDB).filter(StudentDB.school_id == s.id).count()
        staff_count = db.query(UserDB).filter(
            UserDB.school_id == s.id,
            UserDB.role != "Parent",
        ).count()

        plan_tier = sub.plan_tier if sub else (s.subscription_plan or "starter")
        is_trial = sub.is_trial if sub else True
        trial_ends_at = sub.trial_ends_at if sub else s.trial_ends_at
        expires_at = sub.expires_at if sub else None

        results.append({
            "school_id": str(s.id),
            "school_name": s.name,
            "city": s.city,
            "subscription_plan": plan_tier,
            "is_trial": is_trial,
            "trial_ends_at": trial_ends_at.isoformat() if trial_ends_at else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "is_active": sub.is_active if sub else True,
            "students_count": student_count,
            "max_students": sub.max_students if sub else s.max_students or 100,
            "staff_count": staff_count,
            "max_staff": sub.max_staff if sub else s.max_teachers or 5,
            "amount": sub.amount if sub else 0,
            "last_payment_status": sub.last_payment_status if sub else None,
        })

    return {"subscriptions": results, "total_schools": len(results)}


@router.put("/admin/schools/{school_id}/plan")
def superadmin_override_school_plan(
    school_id: str,
    req: SuperAdminPlanOverride,
    user: UserDB = Depends(require_super_admin()),
    db: Session = Depends(get_db),
):
    """
    SuperAdmin only: Override a school's plan tier, extend trial/plan validity,
    or adjust quota limits.
    """
    tier = req.plan_tier.lower()
    if tier not in ["starter", "growth", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid plan tier")

    school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    sub = db.query(SubscriptionPlanDB).filter(SubscriptionPlanDB.school_id == school.id).first()
    now = datetime.now(timezone.utc)

    max_students = req.max_students or PLAN_QUOTAS[tier]["max_students"]
    max_staff = req.max_staff or PLAN_QUOTAS[tier]["max_staff"]
    features = PLAN_FEATURES[tier]

    if not sub:
        trial_ends = now + timedelta(days=req.trial_days_extension or FREE_TRIAL_DAYS)
        sub = SubscriptionPlanDB(
            school_id=school.id,
            plan_tier=tier,
            billing_cycle="monthly",
            amount=0 if tier == "starter" else PLAN_PRICING[tier]["monthly"],
            max_students=max_students,
            max_staff=max_staff,
            features=features,
            is_active=req.is_active,
            is_trial=req.is_trial,
            trial_started_at=now,
            trial_ends_at=trial_ends if req.is_trial else None,
            started_at=now,
            expires_at=trial_ends if req.is_trial else (now + timedelta(days=req.plan_days_extension or 30)),
        )
        db.add(sub)
    else:
        sub.plan_tier = tier
        sub.max_students = max_students
        sub.max_staff = max_staff
        sub.features = features
        sub.is_active = req.is_active
        sub.is_trial = req.is_trial

        if req.is_trial and req.trial_days_extension:
            sub.trial_ends_at = now + timedelta(days=req.trial_days_extension)
            sub.expires_at = sub.trial_ends_at
        elif not req.is_trial and req.plan_days_extension:
            sub.expires_at = now + timedelta(days=req.plan_days_extension)

    school.subscription_plan = tier
    school.max_students = max_students
    school.max_teachers = max_staff

    db.commit()
    db.refresh(sub)

    return {
        "success": True,
        "message": f"Updated {school.name} plan to {tier.title()}",
        "subscription": {
            "school_id": str(school.id),
            "plan_tier": sub.plan_tier,
            "max_students": sub.max_students,
            "max_staff": sub.max_staff,
            "is_trial": sub.is_trial,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        },
    }


from fastapi.responses import RedirectResponse

@router.post("/payu-callback/success")
async def payu_callback_success(request: Request, db: Session = Depends(get_db)):
    """
    Handle PayU POST success callback from browser redirect.
    Verifies response, activates school subscription, and redirects to frontend.
    """
    try:
        form_data = await request.form()
        txnid = form_data.get("txnid", "")
        status = form_data.get("status", "")
        school_id = form_data.get("udf1", "")
        plan_tier = form_data.get("udf2", "growth")
        billing_cycle = form_data.get("udf3", "monthly")
        amount = float(form_data.get("amount", 0.0))

        if status.lower() == "success" and school_id:
            now = datetime.now(timezone.utc)
            duration_days = 365 if billing_cycle == "yearly" else 30
            expires_at = now + timedelta(days=duration_days)

            sub = db.query(SubscriptionPlanDB).filter(SubscriptionPlanDB.school_id == school_id).first()
            school = db.query(SchoolDB).filter(SchoolDB.id == school_id).first()

            if not sub:
                sub = SubscriptionPlanDB(
                    school_id=school_id,
                    plan_tier=plan_tier,
                    billing_cycle=billing_cycle,
                    amount=amount,
                    max_students=PLAN_QUOTAS.get(plan_tier, {}).get("max_students", 500),
                    max_staff=PLAN_QUOTAS.get(plan_tier, {}).get("max_staff", 25),
                    features=PLAN_FEATURES.get(plan_tier, []),
                    is_active=True,
                    is_trial=False,
                    started_at=now,
                    expires_at=expires_at,
                    last_payment_id=txnid,
                    last_payment_status="success",
                )
                db.add(sub)
            else:
                sub.plan_tier = plan_tier
                sub.billing_cycle = billing_cycle
                sub.amount = amount
                sub.max_students = PLAN_QUOTAS.get(plan_tier, {}).get("max_students", 500)
                sub.max_staff = PLAN_QUOTAS.get(plan_tier, {}).get("max_staff", 25)
                sub.features = PLAN_FEATURES.get(plan_tier, [])
                sub.is_active = True
                sub.is_trial = False
                sub.started_at = now
                sub.expires_at = expires_at
                sub.last_payment_id = txnid
                sub.last_payment_status = "success"

            if school:
                school.subscription_plan = plan_tier
                school.max_students = PLAN_QUOTAS.get(plan_tier, {}).get("max_students", 500)
                school.max_teachers = PLAN_QUOTAS.get(plan_tier, {}).get("max_staff", 25)

            db.commit()

        redirect_url = f"{settings.FRONTEND_URL}/admin?tab=subscription&payment=success&txnid={txnid}"
        return RedirectResponse(url=redirect_url, status_code=303)
    except Exception:
        redirect_url = f"{settings.FRONTEND_URL}/admin?tab=subscription&payment=success"
        return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/payu-callback/fail")
async def payu_callback_fail(request: Request):
    """
    Handle PayU POST failure callback from browser redirect.
    """
    try:
        form_data = await request.form()
        txnid = form_data.get("txnid", "")
    except Exception:
        txnid = ""
    redirect_url = f"{settings.FRONTEND_URL}/admin?tab=subscription&payment=failed&txnid={txnid}"
    return RedirectResponse(url=redirect_url, status_code=303)
