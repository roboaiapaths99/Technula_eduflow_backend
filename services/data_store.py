import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / "demo_data" / "class_6A.json"

def load_class_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_students():
    data = load_class_data()
    return data["students"]

def get_exams():
    data = load_class_data()
    return data["exams"]

def get_marks_for_exam(exam_id: str):
    data = load_class_data()
    return [m for m in data["marks"] if m["exam_id"] == exam_id]
