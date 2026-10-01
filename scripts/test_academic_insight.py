import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.gemini_service import generate_academic_summary

sample_student_dashboard = {
    "student": {
        "id": "std_101",
        "name": "Aarav Sharma",
        "grade": "10",
        "section": "A"
    },
    "metrics": {
        "overall_average": 82.5,
        "trend_label": "improving",
        "strongest_subject": "Mathematics",
        "strongest_percentage": 94.0,
        "weakest_subject": "Social Studies",
        "weakest_percentage": 68.0
    },
    "subject_bar": [
        {"subject": "Mathematics", "percentage": 94.0},
        {"subject": "Science", "percentage": 88.0},
        {"subject": "English", "percentage": 80.0},
        {"subject": "Social Studies", "percentage": 68.0}
    ],
    "overall_trend": [
        {"exam_name": "Unit Test 1", "percentage": 78.0},
        {"exam_name": "Mid Term", "percentage": 81.0},
        {"exam_name": "Unit Test 2", "percentage": 82.5}
    ],
    "student_vs_class_subject_avg": [
        {"subject": "Mathematics", "student_percentage": 94.0, "class_average_percentage": 75.0, "delta": 19.0},
        {"subject": "Science", "student_percentage": 88.0, "class_average_percentage": 72.0, "delta": 16.0},
        {"subject": "English", "student_percentage": 80.0, "class_average_percentage": 76.0, "delta": 4.0},
        {"subject": "Social Studies", "student_percentage": 68.0, "class_average_percentage": 74.0, "delta": -6.0}
    ],
    "highlights": [
        {"subject": "Mathematics", "type": "TOP", "rank": 1, "class_size": 40},
        {"subject": "Social Studies", "type": "BOTTOM", "rank": 32, "class_size": 40}
    ]
}

if __name__ == "__main__":
    print("Testing generate_academic_summary with Gemini...")
    insight = generate_academic_summary(sample_student_dashboard)
    print("\nGenerated Academic Insight:")
    print(insight)
