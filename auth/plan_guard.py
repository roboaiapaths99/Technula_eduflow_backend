"""
Plan Guard — Feature gating dependency for SaaS subscription enforcement.

Usage in API endpoints:
    @router.get("/fees/...")
    def list_fees(
        user = Depends(require_role(["Admin"])),
        _plan = Depends(require_feature("fee_management")),
        db = Depends(get_db),
    ):
        ...

If the school's plan does not include the required feature, HTTP 403 is returned
with a clear upgrade prompt message.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user, get_db
from models.school import SchoolDB
from models.user_db import UserDB
from models.subscription_plan_db import SubscriptionPlanDB, PLAN_FEATURES
from models.parent_student_db import ParentStudentDB
from models.student_db import StudentDB
from datetime import datetime, timezone


def require_feature(feature_key: str):
    """
    FastAPI dependency that checks whether the authenticated user's school
    has the given feature enabled in their active subscription plan.

    SuperAdmin and VMS School bypass all plan checks with full feature access.
    Parents and Students receive polite, non-technical notices if a module
    has not been enabled by their school administration.
    """
    def _guard(
        user: UserDB = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # SuperAdmin bypasses plan checks
        if (user.role or "").strip() == "SuperAdmin":
            return True

        is_parent = (user.role or "").strip().lower() in ["parent", "student"]
        parent_friendly_msg = (
            "This module has not been activated by your school administration yet. "
            "Please contact the school office for details."
        )

        effective_school_id = user.school_id
        if not effective_school_id and is_parent:
            link = db.query(ParentStudentDB).filter(
                ParentStudentDB.parent_user_id == user.id
            ).first()
            if link and link.school_id:
                effective_school_id = link.school_id
            elif link and link.student_id:
                st = db.query(StudentDB).filter(StudentDB.id == link.student_id).first()
                if st and st.school_id:
                    effective_school_id = st.school_id

        if not effective_school_id:
            raise HTTPException(
                status_code=403,
                detail=parent_friendly_msg if is_parent else "User is not assigned to any school"
            )

        # Look up school's subscription from DB
        sub = db.query(SubscriptionPlanDB).filter(
            SubscriptionPlanDB.school_id == effective_school_id
        ).first()

        # No subscription record → treat as starter
        if not sub:
            allowed = PLAN_FEATURES.get("starter", [])
            if feature_key not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=parent_friendly_msg if is_parent else f"This feature requires a plan upgrade. '{feature_key}' is not included in your current plan."
                )
            return True

        # Check if subscription is still active (not expired)
        if not sub.is_active:
            raise HTTPException(
                status_code=403,
                detail=parent_friendly_msg if is_parent else "Your subscription has expired. Please renew your plan to continue using this feature."
            )

        now = datetime.now(timezone.utc)

        def _to_utc(dt):
            if dt is None:
                return None
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

        # Check trial expiry
        if sub.is_trial and sub.trial_ends_at:
            if now > _to_utc(sub.trial_ends_at):
                raise HTTPException(
                    status_code=403,
                    detail=parent_friendly_msg if is_parent else "Your free trial has expired. Please upgrade to a paid plan to continue."
                )

        # Check plan expiry for paid plans
        if not sub.is_trial and sub.expires_at:
            if now > _to_utc(sub.expires_at):
                raise HTTPException(
                    status_code=403,
                    detail=parent_friendly_msg if is_parent else "Your subscription has expired. Please renew to continue using this feature."
                )

        # Enterprise plan includes all features unconditionally
        if (sub.plan_tier or "").lower() == "enterprise":
            return True

        # Check if the feature is in the plan's feature list
        plan_features = set(PLAN_FEATURES.get(sub.plan_tier, []) + (sub.features or []))
        if feature_key not in plan_features:
            raise HTTPException(
                status_code=403,
                detail=parent_friendly_msg if is_parent else f"'{feature_key}' is not available in your '{sub.plan_tier}' plan. Please upgrade to unlock this feature."
            )

        return True

    return _guard


def get_school_quota(user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns the school's current quota limits from their subscription.
    Useful for displaying usage bars in the frontend.
    """
    if (user.role or "").strip() == "SuperAdmin":
        return {"max_students": 99999, "max_staff": 99999, "plan_tier": "enterprise"}

    if not user.school_id:
        return {"max_students": 0, "max_staff": 0, "plan_tier": "none"}

    sub = db.query(SubscriptionPlanDB).filter(
        SubscriptionPlanDB.school_id == user.school_id
    ).first()

    if not sub:
        return {"max_students": 100, "max_staff": 5, "plan_tier": "starter"}

    return {
        "max_students": sub.max_students,
        "max_staff": sub.max_staff,
        "plan_tier": sub.plan_tier,
    }
