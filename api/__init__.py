from fastapi import APIRouter

from .students import router as students_router
from .dashboard import router as dashboard_router
from .insights import router as insights_router
from .teacher_upload import router as teacher_upload_router
from .teacher_feedback import router as teacher_feedback_router
from .admin import router as admin_router
from .school_api import router as school_router
from .attendance_api import router as attendance_router
from .risk_api import router as risk_router
from .ticket_api import router as ticket_router
from .announcement_api import router as announcement_router
from .notification_api import router as notification_router
from .report_card_api import router as report_card_router
from .parent_api import router as parent_router
from .admin_stats_api import router as admin_stats_router
from .marks_api import router as marks_router
from .analytics_api import router as analytics_router
from .fee_api import router as fee_router
from .timetable_api import router as timetable_router
from .calendar_api import router as calendar_router
from .leave_api import router as leave_router
from .homework_api import router as homework_router
from .upload_api import router as upload_router
from .chat_api import router as chat_router
from .risk_prediction_api import router as risk_prediction_router
from .exam_sheets_api import router as exam_sheets_router
from .certificate_api import router as certificate_router
from .ptc_api import router as ptc_router
from .diary_api import router as diary_router
from auth.auth_api import router as auth_router
from .superadmin_api import router as superadmin_router
from .parent_code_api import router as parent_code_router
from .subscription_api import router as subscription_router

# 12-Module Expansion & Communication routes
from .gate_pass_api import router as gate_pass_router
from .visitor_log_api import router as visitor_log_router
from .datesheet_api import router as datesheet_router
from .almanac_api import router as almanac_router
from .holiday_api import router as holiday_router
from .gallery_api import router as gallery_router
from .activity_api import router as activity_router
from .parent_profile_api import router as parent_profile_router
from .branding_api import router as branding_router
from .birthday_api import router as birthday_router
from .broadcast_api import router as broadcast_router
from .reports_api import router as reports_router
from .realtime_api import router as realtime_router

api_router = APIRouter()

# Core routes
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(school_router, tags=["School"])
api_router.include_router(students_router, prefix="/students", tags=["Students"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(insights_router, prefix="/insights", tags=["Insights"])
api_router.include_router(teacher_upload_router, prefix="/teacher", tags=["Teacher Upload"])
api_router.include_router(teacher_feedback_router, prefix="/teacher", tags=["Teacher Feedback"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Enterprise Expansion routes
api_router.include_router(attendance_router)
api_router.include_router(risk_router)
api_router.include_router(ticket_router)
api_router.include_router(announcement_router)
api_router.include_router(notification_router)
api_router.include_router(report_card_router)
api_router.include_router(parent_router)
api_router.include_router(admin_stats_router)
api_router.include_router(marks_router)
api_router.include_router(analytics_router)
api_router.include_router(fee_router)
api_router.include_router(timetable_router)
api_router.include_router(calendar_router)
api_router.include_router(leave_router)
api_router.include_router(homework_router)
api_router.include_router(upload_router)
api_router.include_router(chat_router)

# Phase 2 Enterprise Differentiator routes
api_router.include_router(risk_prediction_router)
api_router.include_router(exam_sheets_router)
api_router.include_router(certificate_router)
api_router.include_router(ptc_router)
api_router.include_router(diary_router)

# SaaS Platform Management routes
api_router.include_router(superadmin_router)
api_router.include_router(parent_code_router)
api_router.include_router(subscription_router)

# 12-Module Expansion routers
api_router.include_router(gate_pass_router)
api_router.include_router(visitor_log_router)
api_router.include_router(datesheet_router)
api_router.include_router(almanac_router)
api_router.include_router(holiday_router)
api_router.include_router(gallery_router)
api_router.include_router(activity_router)
api_router.include_router(parent_profile_router)
api_router.include_router(branding_router)
api_router.include_router(birthday_router)
api_router.include_router(broadcast_router)
api_router.include_router(reports_router)
api_router.include_router(realtime_router)

