"""
Auth Service — Password hashing, JWT creation, user creation with school_id.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt
from passlib.context import CryptContext

from core.config import settings
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.user_db import UserDB


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(data: Dict[str, Any], expires_minutes: Optional[int] = None) -> str:
    to_encode = dict(data)
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # Always include school_id in token for tenant isolation
    if "school_id" not in to_encode:
        to_encode["school_id"] = None
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_user(
    db: Session,
    email: str,
    password: str,
    role: str,
    full_name: str | None = None,
    school_id: str | None = None,
    phone: str | None = None,
) -> UserDB:
    """Create a new user with school_id for multi-tenant isolation."""
    email = (email or "").strip().lower()
    role = (role or "").strip()
    full_name = (full_name or "").strip() or None
    password = password or ""

    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    if not password:
        raise HTTPException(status_code=400, detail="password is required")

    import re
    STANDARD_ROLES = ["Parent", "Teacher", "Admin", "ClassTeacher", "SubjectTeacher", "SuperAdmin", "Accountant", "Librarian", "Staff", "Counselor"]
    if not role or len(role) < 2 or len(role) > 50 or not re.match(r'^[A-Za-z0-9_\- ]+$', role):
        raise HTTPException(status_code=400, detail="Role must be 2-50 alphanumeric characters.")

    exists = db.query(UserDB).filter(UserDB.email == email).first()
    if exists:
        raise HTTPException(status_code=400, detail="User already exists")

    u = UserDB(
        email=email,
        full_name=full_name,
        role=role,
        password_hash=hash_password(password),
        school_id=school_id,
        phone=phone,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u
