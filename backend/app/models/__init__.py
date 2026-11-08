"""SQLAlchemy models. Importing this package registers every table on Base.metadata,
which Alembic (alembic/env.py) compares against the migrations."""

from app.models.academic import (
    AcademicTerm,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassSection,
    Enrollment,
    SectionInstructor,
    Subject,
    TimetableEntry,
)
from app.models.audit import AuditLog
from app.models.auth_session import AuthSession
from app.models.college import (
    College,
    CollegeMembership,
    CollegeStatus,
    Department,
    Invite,
    MembershipKind,
    MembershipStatus,
    Role,
    RoleGrant,
    RosterEntry,
    VerificationFlag,
)
from app.models.community import (
    Comment,
    ContentReport,
    ContentStatus,
    Post,
    PostVisibility,
    Reaction,
    ReportReason,
    ReportStatus,
)
from app.models.issue import (
    CampusIssue,
    IssueCategory,
    IssueStatus,
    IssueUpdate,
    IssueUpdateKind,
)
from app.models.notice import (
    Notice,
    NoticeCategory,
    NoticePriority,
    NoticeScope,
    NoticeStatus,
)
from app.models.notification import Notification, NotificationType
from app.models.rate_limit import RateLimitCounter
from app.models.user import PlatformRole, User, UserStatus
from app.models.user_token import TokenPurpose, UserToken

__all__ = [
    "AcademicTerm",
    "AttendanceRecord",
    "AttendanceSession",
    "AttendanceStatus",
    "AuditLog",
    "AuthSession",
    "CampusIssue",
    "ClassSection",
    "College",
    "CollegeMembership",
    "CollegeStatus",
    "Comment",
    "ContentReport",
    "ContentStatus",
    "Department",
    "Enrollment",
    "Invite",
    "IssueCategory",
    "IssueStatus",
    "IssueUpdate",
    "IssueUpdateKind",
    "MembershipKind",
    "MembershipStatus",
    "Notice",
    "NoticeCategory",
    "NoticePriority",
    "NoticeScope",
    "NoticeStatus",
    "Notification",
    "NotificationType",
    "PlatformRole",
    "Post",
    "PostVisibility",
    "RateLimitCounter",
    "Reaction",
    "ReportReason",
    "ReportStatus",
    "Role",
    "RoleGrant",
    "RosterEntry",
    "SectionInstructor",
    "Subject",
    "TimetableEntry",
    "TokenPurpose",
    "User",
    "UserStatus",
    "UserToken",
    "VerificationFlag",
]
