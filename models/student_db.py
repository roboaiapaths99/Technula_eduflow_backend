"""
Student model — enhanced with school_id, roll_no, gender, dob, photo.
"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from db.base import Base, GUID
import uuid
from datetime import datetime, timezone


class StudentDB(Base):
    __tablename__ = "students"

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    school_id = Column(GUID, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    admission_no = Column(String(50), nullable=False)
    roll_no = Column(String(20), nullable=True)
    grade = Column(String(10), nullable=False)
    section = Column(String(10), nullable=False)
    gender = Column(String(10), nullable=True)  # Male, Female, Other
    dob = Column(Date, nullable=True)
    photo_url = Column(String(500), nullable=True)
    blood_group = Column(String(10), nullable=True)  # O+, A+, B+, AB+, O-, A-, B-, AB-
    father_name = Column(String(100), nullable=True)
    father_phone = Column(String(20), nullable=True)
    mother_name = Column(String(100), nullable=True)
    mother_phone = Column(String(20), nullable=True)
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(20), nullable=True)
    address = Column(String(500), nullable=True)
    medical_notes = Column(String(500), nullable=True)
    previous_school = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "admission_no", name="uq_students_school_admission"),
        Index("ix_students_school_grade_sec", "school_id", "grade", "section"),
    )

    # Relationships
    school = relationship("SchoolDB", back_populates="students")
    marks = relationship("Mark", back_populates="student", cascade="all, delete-orphan")
    attendance_records = relationship("AttendanceDB", back_populates="student", cascade="all, delete-orphan")
    parent_links = relationship("ParentStudentDB", back_populates="student")
    feedback = relationship("TeacherFeedback", back_populates="student", cascade="all, delete-orphan")
    risk_cases = relationship("RiskCaseDB", back_populates="student", cascade="all, delete-orphan")
    diary_entries = relationship("StudentDiaryEntryDB", back_populates="student", cascade="all, delete-orphan")
