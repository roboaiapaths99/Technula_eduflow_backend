"""
Multi-Tenant Auth Dependencies — the security backbone of the SaaS platform.
Provides:
  - get_current_user: JWT → UserDB lookup
  - require_role: role-based access with SuperAdmin bypass
  - require_super_admin: SuperAdmin-only endpoints
  - require_school_match: ensures user can only access their own school's data
  - get_tenant_school_id: extracts school_id from JWT user for query filtering
"""
from typing import Optional, List

from fastapi import Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

from db.session import SessionLocal
from core.config import settings
from models.user_db import UserDB

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    header_token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
    db=Depends(get_db)
) -> Optional[UserDB]:
    """Extracts user from Bearer header or ?token= query parameter; returns None if missing or invalid without raising."""
    token = header_token or query_token
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(UserDB).filter(UserDB.id == user_id).first()
    except Exception:
        return None


def get_current_user(
    header_token: Optional[str] = Depends(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
    db=Depends(get_db)
) -> UserDB:
    token = header_token or query_token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Block suspended schools — except SuperAdmin who isn't tied to a school
    if user.role != "SuperAdmin" and user.school_id:
        from models.school import SchoolDB
        school = db.query(SchoolDB).filter(SchoolDB.id == user.school_id).first()
        if school and getattr(school, "is_suspended", False):
            raise HTTPException(
                status_code=403,
                detail="Your school account has been suspended. Please contact support."
            )

    return user


def require_role(roles: List[str]):
    """
    Role-based guard. SuperAdmin bypasses all role checks.
    Usage: user = Depends(require_role(["Admin", "Teacher"]))
    """
    def _guard(user: UserDB = Depends(get_current_user)) -> UserDB:
        user_role = (user.role or "").strip().lower()

        # SuperAdmin can do anything
        if user_role == "superadmin":
            return user

        normalized_roles = [r.strip().lower() for r in roles]

        # Admin group: Admin, Principal, Vice_Principal, SchoolAdmin, Director
        admin_group = {"admin", "principal", "vice_principal", "vice-principal", "schooladmin", "director"}
        # Teacher group: Teacher, ClassTeacher, SubjectTeacher, Staff
        teacher_group = {"teacher", "classteacher", "subjectteacher", "staff", "head_teacher"}

        # If user is in admin group and endpoint allows admin
        if user_role in admin_group and any(r in admin_group for r in normalized_roles):
            return user

        # If user is in teacher group and endpoint allows teacher or staff
        if user_role in teacher_group and any(r in teacher_group for r in normalized_roles):
            return user

        # Direct match
        if user_role in normalized_roles:
            return user

        # Admins can access teacher / staff / parent endpoints within their school
        if user_role in admin_group:
            return user

        raise HTTPException(status_code=403, detail="Forbidden")
    return _guard


def require_super_admin():
    """Only the SaaS platform owner (SuperAdmin) can access."""
    def _guard(user: UserDB = Depends(get_current_user)) -> UserDB:
        if (user.role or "").strip() != "SuperAdmin":
            raise HTTPException(status_code=403, detail="SuperAdmin access required")
        return user
    return _guard


def get_tenant_school_id(user: UserDB = Depends(get_current_user)) -> str:
    """
    Extracts school_id from the authenticated user's JWT/profile.
    Non-SuperAdmin users MUST have a school_id.
    SuperAdmin gets None (they can access all schools).
    """
    if (user.role or "").strip() == "SuperAdmin":
        return None  # SuperAdmin is cross-tenant
    if not user.school_id:
        raise HTTPException(
            status_code=403,
            detail="User is not assigned to any school"
        )
    return str(user.school_id)


def require_school_match(user: UserDB, resource_school_id: str):
    """
    Enforce that a non-SuperAdmin user can only access their own school's data.
    Call this in any endpoint that receives a school_id from path/query params.
    SuperAdmin bypasses this check.
    """
    if (user.role or "").strip() == "SuperAdmin":
        return  # SuperAdmin can access any school

    if not user.school_id:
        raise HTTPException(status_code=403, detail="User not assigned to any school")

    if str(user.school_id) != str(resource_school_id):
        raise HTTPException(
            status_code=403,
            detail="Access denied: you cannot access another school's data"
        )
