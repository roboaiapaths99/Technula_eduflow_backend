# Register all models with SQLAlchemy Base
from .school import SchoolDB  # noqa: F401
from .user_db import UserDB  # noqa: F401
from .student_db import StudentDB  # noqa: F401
from .subject import Subject  # noqa: F401
from .exam import Exam  # noqa: F401
from .marks import Mark  # noqa: F401
from .attendance_db import AttendanceDB  # noqa: F401
from .risk_case_db import RiskCaseDB  # noqa: F401
from .announcement_db import AnnouncementDB  # noqa: F401
from .ticket_db import TicketDB  # noqa: F401
from .notification_db import NotificationDB  # noqa: F401
from .parent_student_db import ParentStudentDB  # noqa: F401
from .teacher_assignment_db import TeacherAssignmentDB  # noqa: F401
from .teacher_feedback import TeacherFeedback  # noqa: F401
from .school_payment_config_db import SchoolPaymentConfigDB  # noqa: F401
from .fee_structure_db import FeeStructureDB  # noqa: F401
from .fee_payment_db import FeePaymentDB  # noqa: F401
from .timetable_db import TimetableSlotDB  # noqa: F401
from .school_calendar_db import SchoolCalendarEventDB  # noqa: F401
from .leave_request_db import LeaveRequestDB  # noqa: F401
from .homework_db import HomeworkDB, HomeworkSubmissionDB  # noqa: F401
from .chat_message_db import ChatMessageDB  # noqa: F401
from .student_exam_sheet_db import StudentExamSheetDB  # noqa: F401
from .certificate_db import SchoolAssetDB, CertificateRequestDB  # noqa: F401
from .ptc_db import PTCEventDB, PTCSlotDB, PTCBookingDB  # noqa: F401
from .student_diary_db import StudentDiaryEntryDB  # noqa: F401
from .parent_link_code_db import ParentLinkCodeDB  # noqa: F401
from .audit_log_db import AuditLogDB  # noqa: F401
from .subscription_plan_db import SubscriptionPlanDB  # noqa: F401
from .gate_pass_db import GatePassDB, GatePassStatusLogDB  # noqa: F401
from .visitor_log_db import VisitorLogDB  # noqa: F401
from .datesheet_db import DatesheetDB, DatesheetEntryDB  # noqa: F401
from .almanac_db import AlmanacDB  # noqa: F401
from .holiday_db import HolidayDB  # noqa: F401
from .gallery_db import GalleryAlbumDB, GalleryPhotoDB  # noqa: F401
from .activity_db import ActivityDB  # noqa: F401
from .profile_change_request_db import ProfileChangeRequestDB  # noqa: F401
from .otp_token_db import OtpTokenDB  # noqa: F401
