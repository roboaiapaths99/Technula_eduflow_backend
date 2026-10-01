from pydantic import BaseModel
from datetime import date


class Assessment(BaseModel):
    id: int
    student_id: int
    subject: str
    exam_name: str
    exam_date: date
    score: float
    max_score: float
