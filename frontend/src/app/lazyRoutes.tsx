import { lazyNamed } from "./lazyNamed";

/** The split sections (NFR-PERF-002). Each `import()` is one chunk. */

const manage = () => import("./sections/manage");
const platform = () => import("./sections/platform");
const teaching = () => import("./sections/teaching");
const academics = () => import("./sections/academics");
const noticeEditor = () => import("@/features/notices/NoticeEditorPage");

export const RequestsTab = lazyNamed(manage, "RequestsTab");
export const MembersTab = lazyNamed(manage, "MembersTab");
export const InvitesTab = lazyNamed(manage, "InvitesTab");
export const DepartmentsTab = lazyNamed(manage, "DepartmentsTab");
export const RosterTab = lazyNamed(manage, "RosterTab");
export const AuditTab = lazyNamed(manage, "AuditTab");
export const ModerationTab = lazyNamed(manage, "ModerationTab");
export const AcademicsAdminTab = lazyNamed(manage, "AcademicsAdminTab");
export const SectionSetupPage = lazyNamed(manage, "SectionSetupPage");

export const CollegesTab = lazyNamed(platform, "CollegesTab");
export const CollegeDetailPage = lazyNamed(platform, "CollegeDetailPage");
export const UsersTab = lazyNamed(platform, "UsersTab");
export const PlatformAuditTab = lazyNamed(platform, "PlatformAuditTab");

export const TeachingPage = lazyNamed(teaching, "TeachingPage");
export const SectionPage = lazyNamed(teaching, "SectionPage");
export const NewAttendancePage = lazyNamed(teaching, "NewAttendancePage");
export const AttendanceSessionPage = lazyNamed(teaching, "AttendanceSessionPage");
export const AssessmentPage = lazyNamed(teaching, "AssessmentPage");

export const TimetableTab = lazyNamed(academics, "TimetableTab");
export const AttendanceTab = lazyNamed(academics, "AttendanceTab");
export const SubjectAttendancePage = lazyNamed(academics, "SubjectAttendancePage");
export const ResultsTab = lazyNamed(academics, "ResultsTab");

export const NewNoticePage = lazyNamed(noticeEditor, "NewNoticePage");
export const EditNoticePage = lazyNamed(noticeEditor, "EditNoticePage");
