from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from db.session import SessionLocal
from models.student_db import StudentDB
from models.assessment import Assessment
from models.exam import Exam
from models.marks import Mark
from models.subject import Subject


# ──────────────────────────────────────────
# Keep the same Student shape used by UI/API
# ──────────────────────────────────────────
@dataclass
class Student:
    id: int
    name: str
    grade: str
    section: str

    def dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "grade": self.grade,
            "section": self.section,
        }


def _db() -> Session:
    return SessionLocal()


def _to_student(s: StudentDB) -> Student:
    return Student(id=s.id, name=s.name, grade=s.grade, section=s.section)


def _subject_names(db: Session) -> List[str]:
    rows = db.query(Subject).order_by(Subject.name.asc()).all()
    return [r.name for r in rows]


def list_students() -> list[Student]:
    """
    Used by /students endpoint.
    Now returns DB students instead of demo.
    """
    db = _db()
    try:
        rows = db.query(StudentDB).order_by(StudentDB.id.asc()).all()
        return [_to_student(s) for s in rows]
    finally:
        db.close()


def get_student(student_id: int) -> Student | None:
    """
    Used by parent dashboard selection.
    """
    db = _db()
    try:
        s = db.query(StudentDB).filter(StudentDB.id == student_id).first()
        return _to_student(s) if s else None
    finally:
        db.close()


def get_admission_no(student_id: int) -> str:
    """
    Used by some parent class-insights helpers.
    Now reads from DB.
    """
    db = _db()
    try:
        s = db.query(StudentDB).filter(StudentDB.id == student_id).first()
        return (s.admission_no if s and s.admission_no else f"DEMO-{student_id:03d}")
    finally:
        db.close()


def list_class_students(grade: str, section: str) -> list[Student]:
    """
    Class roster from DB.
    """
    db = _db()
    try:
        rows = (
            db.query(StudentDB)
            .filter(StudentDB.grade == str(grade), StudentDB.section == str(section).upper())
            .order_by(StudentDB.id.asc())
            .all()
        )
        return [_to_student(s) for s in rows]
    finally:
        db.close()


def get_student_assessments(student_id: int) -> list[Assessment]:
    """
    Returns DB marks as Assessment objects for existing dashboard logic.
    """
    db = _db()
    try:
        rows = (
            db.query(Mark, Exam, Subject)
            .join(Exam, Mark.exam_id == Exam.id)
            .join(Subject, Mark.subject_id == Subject.id)
            .filter(Mark.student_id == student_id)
            .order_by(Exam.exam_date.asc(), Exam.id.asc(), Subject.name.asc(), Mark.id.asc())
            .all()
        )

        out: List[Assessment] = []
        for m, e, sub in rows:
            out.append(
                Assessment(
                    id=m.id,
                    student_id=student_id,
                    subject=sub.name,
                    exam_name=e.exam_name,
                    exam_date=e.exam_date,
                    score=float(m.marks_obtained),
                    max_score=float(m.max_marks),
                    percentage=round((float(m.marks_obtained) / float(m.max_marks)) * 100, 1) if m.max_marks else 0.0,
                )
            )
        return out
    finally:
        db.close()


# ──────────────────────────────────────────
# Existing compute_dashboard (KEEP SHAPE)
# ──────────────────────────────────────────
def compute_dashboard(student_id: int) -> Dict[str, Any]:
    """
    Existing dashboard computation for selected student.
    Kept shape to avoid breaking current parent dashboard.
    Now uses DB assessments.
    """
    student = get_student(student_id)
    if not student:
        raise ValueError("Student not found")

    assessments = get_student_assessments(student_id)
    if not assessments:
        return {
            "student": student.dict(),
            "metrics": {},
            "subject_bar": [],
            "overall_trend": [],
        }

    total_score = sum(a.score for a in assessments)
    total_max = sum(a.max_score for a in assessments)
    overall_avg = round((total_score / total_max) * 100, 1) if total_max > 0 else 0.0

    latest_date = max(a.exam_date for a in assessments)
    latest_assessments = [a for a in assessments if a.exam_date == latest_date]

    subject_bar = [
        {
            "subject": a.subject,
            "score": a.score,
            "max_score": a.max_score,
            "percentage": round((a.score / a.max_score) * 100, 1) if a.max_score > 0 else 0.0,
        }
        for a in latest_assessments
    ]

    strongest = max(subject_bar, key=lambda x: x["percentage"])
    weakest = min(subject_bar, key=lambda x: x["percentage"])

    trend_map: Dict[str, Dict[str, float]] = {}
    for a in assessments:
        key = a.exam_name
        d = trend_map.setdefault(key, {"total": 0.0, "max": 0.0})
        d["total"] += a.score
        d["max"] += a.max_score

    overall_trend = []
    exam_order: Dict[str, date] = {}
    for a in assessments:
        exam_order.setdefault(a.exam_name, a.exam_date)

    for exam_name, exam_date in sorted(exam_order.items(), key=lambda x: x[1]):
        d = trend_map[exam_name]
        perc = round((d["total"] / d["max"]) * 100, 1) if d["max"] > 0 else 0.0
        overall_trend.append(
            {"exam_name": exam_name, "exam_date": exam_date.isoformat(), "percentage": perc}
        )

    trend_label = "Stable"
    delta = 0.0
    if len(overall_trend) >= 2:
        delta = overall_trend[-1]["percentage"] - overall_trend[0]["percentage"]
        if delta > 5:
            trend_label = "Improving"
        elif delta < -5:
            trend_label = "Declining"

    metrics = {
        "overall_average": overall_avg,
        "strongest_subject": strongest["subject"],
        "strongest_percentage": strongest["percentage"],
        "weakest_subject": weakest["subject"],
        "weakest_percentage": weakest["percentage"],
        "trend_label": trend_label,
        # NEW (non-breaking): brief explanation + calc
        "trend_explanation": (
            "Trend analysis summarizes how the student's overall percentage changes across exams. "
            "For each exam, we compute: (sum of subject scores / sum of subject max) × 100. "
            "Then we compare the first exam vs the latest exam: if the change is > +5%, it's Improving; "
            "if < -5%, it's Declining; otherwise Stable."
        ),
        "trend_delta_percentage_points": round(delta, 1),
    }

    return {
        "student": student.dict(),
        "metrics": metrics,
        "subject_bar": subject_bar,
        "overall_trend": overall_trend,
    }


# ──────────────────────────────────────────
# Class analytics (Parent features) – now DB-based
# ──────────────────────────────────────────
def _latest_exam_date_for_class(db: Session, student_ids: List[int], exam_name: str) -> date | None:
    d = (
        db.query(Exam.exam_date)
        .join(Mark, Mark.exam_id == Exam.id)
        .filter(Mark.student_id.in_(student_ids), Exam.exam_name == exam_name)
        .order_by(Exam.exam_date.desc())
        .first()
    )
    return d[0] if d else None


def _overall_percentage_for_exam(db: Session, student_id: int, exam_name: str, exam_date: date) -> float:
    rows = (
        db.query(Mark, Exam)
        .join(Exam, Mark.exam_id == Exam.id)
        .filter(Mark.student_id == student_id, Exam.exam_name == exam_name, Exam.exam_date == exam_date)
        .all()
    )
    if not rows:
        return 0.0
    total_score = sum(float(m.marks_obtained) for m, _e in rows)
    total_max = sum(float(m.max_marks) for m, _e in rows)
    return round((total_score / total_max) * 100, 1) if total_max > 0 else 0.0


def class_top_avg_bottom_for_exam(grade: str, section: str, exam_name: str) -> Dict[str, Any]:
    class_students = list_class_students(grade, section)
    if not class_students:
        return {"topper": None, "bottom": None, "class_avg": None, "class_size": 0}

    student_ids = [s.id for s in class_students]

    db = _db()
    try:
        exam_date = _latest_exam_date_for_class(db, student_ids, exam_name)
        if not exam_date:
            return {"topper": None, "bottom": None, "class_avg": None, "class_size": len(class_students)}

        rows = []
        for s in class_students:
            pct = _overall_percentage_for_exam(db, s.id, exam_name, exam_date)

            subj_rows = (
                db.query(Mark, Exam, Subject)
                .join(Exam, Mark.exam_id == Exam.id)
                .join(Subject, Mark.subject_id == Subject.id)
                .filter(Mark.student_id == s.id, Exam.exam_name == exam_name, Exam.exam_date == exam_date)
                .order_by(Subject.name.asc())
                .all()
            )

            subj = [
                {
                    "subject": sub.name,
                    "score": float(m.marks_obtained),
                    "max_score": float(m.max_marks),
                    "percentage": round((float(m.marks_obtained) / float(m.max_marks)) * 100, 1) if m.max_marks else 0.0,
                }
                for (m, _e, sub) in subj_rows
            ]

            rows.append(
                {
                    "student_id": s.id,
                    "admission_no": get_admission_no(s.id),
                    "name": s.name,
                    "percentage": pct,
                    "subject_marks": subj,
                }
            )

        rows.sort(key=lambda x: x["percentage"], reverse=True)
        class_avg = round(sum(r["percentage"] for r in rows) / len(rows), 1) if rows else 0.0

        return {
            "exam_name": exam_name,
            "exam_date": exam_date.isoformat(),
            "class_size": len(rows),
            "class_avg": class_avg,
            "topper": rows[0] if rows else None,
            "bottom": rows[-1] if rows else None,
        }
    finally:
        db.close()


def subject_wise_class_stats_for_exam(grade: str, section: str, exam_name: str) -> List[Dict[str, Any]]:
    """
    NEW (non-breaking): Subject-wise stats for the selected class+exam.
    Returns per subject:
      - class_average_percentage
      - subject_max_percentage
      - subject_min_percentage
    """
    class_students = list_class_students(grade, section)
    if not class_students:
        return []

    student_ids = [s.id for s in class_students]

    db = _db()
    try:
        exam_date = _latest_exam_date_for_class(db, student_ids, exam_name)
        if not exam_date:
            return []

        subjects = _subject_names(db)
        out: List[Dict[str, Any]] = []

        for sub_name in subjects:
            rows = (
                db.query(Mark, Exam, Subject)
                .join(Exam, Mark.exam_id == Exam.id)
                .join(Subject, Mark.subject_id == Subject.id)
                .filter(
                    Mark.student_id.in_(student_ids),
                    Exam.exam_name == exam_name,
                    Exam.exam_date == exam_date,
                    Subject.name == sub_name,
                )
                .all()
            )
            if not rows:
                continue

            percs: List[float] = []
            for m, _e, _s in rows:
                if not m.max_marks:
                    percs.append(0.0)
                else:
                    percs.append(round((float(m.marks_obtained) / float(m.max_marks)) * 100, 1))

            if not percs:
                continue

            out.append(
                {
                    "subject": sub_name,
                    "class_average_percentage": round(sum(percs) / len(percs), 1),
                    "subject_max_percentage": round(max(percs), 1),
                    "subject_min_percentage": round(min(percs), 1),
                }
            )

        return out
    finally:
        db.close()


def subject_wise_class_average_for_exam(grade: str, section: str, exam_name: str) -> List[Dict[str, Any]]:
    class_students = list_class_students(grade, section)
    if not class_students:
        return []

    student_ids = [s.id for s in class_students]

    db = _db()
    try:
        exam_date = _latest_exam_date_for_class(db, student_ids, exam_name)
        if not exam_date:
            return []

        subjects = _subject_names(db)
        out = []

        for sub_name in subjects:
            rows = (
                db.query(Mark, Exam, Subject)
                .join(Exam, Mark.exam_id == Exam.id)
                .join(Subject, Mark.subject_id == Subject.id)
                .filter(
                    Mark.student_id.in_(student_ids),
                    Exam.exam_name == exam_name,
                    Exam.exam_date == exam_date,
                    Subject.name == sub_name,
                )
                .all()
            )
            if not rows:
                continue

            total = sum(float(m.marks_obtained) for (m, _e, _s) in rows)
            total_max = sum(float(m.max_marks) for (m, _e, _s) in rows)
            pct = round((total / total_max) * 100, 1) if total_max > 0 else 0.0

            out.append({"subject": sub_name, "class_average_percentage": pct})

        return out
    finally:
        db.close()


def student_vs_class_subject_average(student_id: int, exam_name: str) -> List[Dict[str, Any]]:
    student = get_student(student_id)
    if not student:
        return []

    # NEW: get avg+max+min per subject (so UI can show bar chart: student vs avg vs max vs min)
    stats_rows = subject_wise_class_stats_for_exam(student.grade, student.section, exam_name)
    stats_map = {x["subject"]: x for x in stats_rows}

    db = _db()
    try:
        # latest exam date for this student + exam_name
        d = (
            db.query(Exam.exam_date)
            .join(Mark, Mark.exam_id == Exam.id)
            .filter(Mark.student_id == student_id, Exam.exam_name == exam_name)
            .order_by(Exam.exam_date.desc())
            .first()
        )
        if not d:
            return []
        latest_date = d[0]

        rows = (
            db.query(Mark, Exam, Subject)
            .join(Exam, Mark.exam_id == Exam.id)
            .join(Subject, Mark.subject_id == Subject.id)
            .filter(Mark.student_id == student_id, Exam.exam_name == exam_name, Exam.exam_date == latest_date)
            .order_by(Subject.name.asc())
            .all()
        )

        out = []
        for m, _e, sub in rows:
            student_pct = round((float(m.marks_obtained) / float(m.max_marks)) * 100, 1) if m.max_marks else 0.0

            st = stats_map.get(sub.name, {})
            class_avg = float(st.get("class_average_percentage", 0.0))
            class_max = float(st.get("subject_max_percentage", 0.0))
            class_min = float(st.get("subject_min_percentage", 0.0))

            out.append(
                {
                    "subject": sub.name,
                    "student_percentage": student_pct,
                    "class_average_percentage": class_avg,
                    "subject_max_percentage": class_max,
                    "subject_min_percentage": class_min,
                    "delta": round(student_pct - class_avg, 1),
                }
            )

        return out
    finally:
        db.close()


def subject_top_bottom_highlights(student_id: int, exam_name: str, top_n: int = 5) -> List[Dict[str, Any]]:
    student = get_student(student_id)
    if not student:
        return []

    class_students = list_class_students(student.grade, student.section)
    if not class_students:
        return []

    student_ids = [s.id for s in class_students]

    db = _db()
    try:
        exam_date = _latest_exam_date_for_class(db, student_ids, exam_name)
        if not exam_date:
            return []

        subjects = _subject_names(db)
        highlights: List[Dict[str, Any]] = []
        class_size = len(student_ids)

        for sub_name in subjects:
            rows = (
                db.query(Mark, Subject)
                .join(Subject, Mark.subject_id == Subject.id)
                .join(Exam, Mark.exam_id == Exam.id)
                .filter(
                    Mark.student_id.in_(student_ids),
                    Exam.exam_name == exam_name,
                    Exam.exam_date == exam_date,
                    Subject.name == sub_name,
                )
                .all()
            )
            if not rows:
                continue

            # sort by marks_obtained desc
            rows_sorted = sorted(rows, key=lambda x: float(x[0].marks_obtained), reverse=True)

            # rank + student row
            rank = None
            student_row = None
            for i, (m, _sub) in enumerate(rows_sorted, start=1):
                if m.student_id == student_id:
                    rank = i
                    student_row = m
                    break
            if not rank or not student_row:
                continue

            topper_row = rows_sorted[0][0]

            total = sum(float(m.marks_obtained) for (m, _sub) in rows_sorted)
            total_max = sum(float(m.max_marks) for (m, _sub) in rows_sorted)
            class_avg_pct = round((total / total_max) * 100, 1) if total_max > 0 else 0.0

            student_pct = round((float(student_row.marks_obtained) / float(student_row.max_marks)) * 100, 1) if student_row.max_marks else 0.0
            topper_pct = round((float(topper_row.marks_obtained) / float(topper_row.max_marks)) * 100, 1) if topper_row.max_marks else 0.0

            if rank <= top_n:
                h_type = "TOP"
            elif rank > class_size - top_n:
                h_type = "BOTTOM"
            else:
                continue

            highlights.append(
                {
                    "subject": sub_name,
                    "type": h_type,
                    "rank": rank,
                    "class_size": class_size,
                    "student_score": float(student_row.marks_obtained),
                    "student_max_score": float(student_row.max_marks),
                    "student_percentage": student_pct,
                    "topper_score": float(topper_row.marks_obtained),
                    "topper_max_score": float(topper_row.max_marks),
                    "topper_percentage": topper_pct,
                    "class_average_percentage": class_avg_pct,
                }
            )

        return highlights
    finally:
        db.close()


def class_trend_for_exams(grade: str, section: str, exam_names: List[str]) -> List[Dict[str, Any]]:
    class_students = list_class_students(grade, section)
    if not class_students:
        return []

    student_ids = [s.id for s in class_students]
    out: List[Dict[str, Any]] = []

    db = _db()
    try:
        for exam_name in exam_names:
            exam_date = _latest_exam_date_for_class(db, student_ids, exam_name)
            if not exam_date:
                continue

            percs = [_overall_percentage_for_exam(db, sid, exam_name, exam_date) for sid in student_ids]
            if not percs:
                continue

            out.append(
                {
                    "exam_name": exam_name,
                    "exam_date": exam_date.isoformat(),
                    "class_average": round(sum(percs) / len(percs), 1),
                    "topper": round(max(percs), 1),
                    "bottom": round(min(percs), 1),
                }
            )

        out.sort(key=lambda x: x["exam_date"])
        return out
    finally:
        db.close()


def compute_parent_class_insights(student_id: int, exam_name: str = "Final") -> Dict[str, Any]:
    """
    Returns all parent class insights.
    Kept same keys as before.
    """
    student = get_student(student_id)
    if not student:
        raise ValueError("Student not found")

    class_students = list_class_students(student.grade, student.section)
    if not class_students:
        return {
            "class_summary": {},
            "student_vs_class_subject_avg": [],
            "highlights": [],
            "class_trend": [],
        }

    # Determine exam order from student's own DB assessments
    student_assessments = get_student_assessments(student_id)
    exam_order: Dict[str, date] = {}
    for a in student_assessments:
        exam_order.setdefault(a.exam_name, a.exam_date)
    ordered_exam_names = [k for k, _ in sorted(exam_order.items(), key=lambda x: x[1])]

    class_summary = class_top_avg_bottom_for_exam(student.grade, student.section, exam_name)

    # NEW: add student's own overall % for the currently selected exam (same exam_date used by class_summary)
    try:
        if class_summary and class_summary.get("exam_date"):
            exam_date = date.fromisoformat(class_summary["exam_date"])
            db = _db()
            try:
                student_pct = _overall_percentage_for_exam(db, student_id, exam_name, exam_date)
            finally:
                db.close()
            class_summary["student_percentage"] = student_pct
    except Exception:
        # keep non-breaking; UI can ignore if not present
        pass

    return {
        "class_summary": class_summary,
        "student_vs_class_subject_avg": student_vs_class_subject_average(student_id, exam_name),
        "highlights": subject_top_bottom_highlights(student_id, exam_name, top_n=5),
        "class_trend": class_trend_for_exams(student.grade, student.section, ordered_exam_names),
        # NEW (optional/non-breaking): explicit subject stats list for easy table rendering
        "class_subject_stats": subject_wise_class_stats_for_exam(student.grade, student.section, exam_name),
    }
