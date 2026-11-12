import { Navigate, type RouteObject } from "react-router";

import { AcademicsLayout } from "@/features/academic/AcademicsLayout";
import { TeachingGuard } from "@/features/academic/TeachingGuard";
import { ManageLayout, RequireCapability } from "@/features/admin/ManageLayout";
import { AccountPage } from "@/features/auth/AccountPage";
import { CheckEmailPage } from "@/features/auth/CheckEmailPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { GuestOnly, HomeRedirect, RequireAuth, RequireCampus } from "@/features/auth/guards";
import { NotFoundPage } from "@/features/auth/NotFoundPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { SignInPage } from "@/features/auth/SignInPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { HomePage } from "@/features/campus/HomePage";
import { InviteAcceptPage } from "@/features/campus/InviteAcceptPage";
import { JoinPage } from "@/features/campus/JoinPage";
import { PlatformLayout } from "@/features/platform/PlatformLayout";
import { CommunityPage } from "@/features/community/CommunityPage";
import { PostPage } from "@/features/community/PostPage";
import { IssuePage } from "@/features/issues/IssuePage";
import { IssuesPage } from "@/features/issues/IssuesPage";
import { ReportIssuePage } from "@/features/issues/ReportIssuePage";
import { DepartmentPage } from "@/features/notices/DepartmentPage";
import { NoticePage } from "@/features/notices/NoticePage";
import { NoticesPage } from "@/features/notices/NoticesPage";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";
import { StatusPage } from "@/features/system-status/StatusPage";

import {
  AcademicsAdminTab,
  AssessmentPage,
  AttendanceSessionPage,
  AttendanceTab,
  AuditTab,
  CollegeDetailPage,
  CollegesTab,
  DepartmentsTab,
  EditNoticePage,
  InvitesTab,
  MembersTab,
  ModerationTab,
  NewAttendancePage,
  NewNoticePage,
  PlatformAuditTab,
  RequestsTab,
  ResultsTab,
  RosterTab,
  SectionPage,
  SectionSetupPage,
  SubjectAttendancePage,
  TeachingPage,
  TimetableTab,
  UsersTab,
} from "./lazyRoutes";
import { AppShell } from "./shells/AppShell";
import { AuthShell } from "./shells/AuthShell";

/**
 * Signed-out screens use the centred AuthShell; signed-in ones the AppShell with navigation.
 * Paths for emailed links (/verify-email, /reset-password, /invites/accept, /sign-in,
 * /forgot-password) are fixed by the backend's email templates.
 */
export const routes: RouteObject[] = [
  {
    element: <AuthShell />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <GuestOnly />,
        children: [
          { path: "sign-in", element: <SignInPage /> },
          { path: "register", element: <RegisterPage /> },
        ],
      },
      { path: "forgot-password", element: <ForgotPasswordPage /> },
      { path: "check-email", element: <CheckEmailPage /> },
      { path: "verify-email", element: <VerifyEmailPage /> },
      { path: "reset-password", element: <ResetPasswordPage /> },
      { path: "invites/accept", element: <InviteAcceptPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "home", element: <HomePage /> },
          {
            element: <RequireCampus />,
            children: [
              { path: "notices", element: <NoticesPage /> },
              { path: "notices/new", element: <NewNoticePage /> },
              { path: "notices/:noticeId", element: <NoticePage /> },
              { path: "notices/:noticeId/edit", element: <EditNoticePage /> },
              { path: "departments/:departmentId", element: <DepartmentPage /> },
              {
                path: "academics",
                element: <AcademicsLayout />,
                children: [
                  { index: true, element: <Navigate to="timetable" replace /> },
                  { path: "timetable", element: <TimetableTab /> },
                  { path: "attendance", element: <AttendanceTab /> },
                  { path: "attendance/:sectionId", element: <SubjectAttendancePage /> },
                  { path: "results", element: <ResultsTab /> },
                ],
              },
              {
                path: "teaching",
                element: <TeachingGuard />,
                children: [
                  { index: true, element: <TeachingPage /> },
                  { path: "sections/:sectionId", element: <SectionPage /> },
                  { path: "sections/:sectionId/attendance/new", element: <NewAttendancePage /> },
                  { path: "sessions/:sessionId", element: <AttendanceSessionPage /> },
                  { path: "assessments/:assessmentId", element: <AssessmentPage /> },
                ],
              },
              { path: "community", element: <CommunityPage /> },
              { path: "community/posts/:postId", element: <PostPage /> },
              { path: "issues", element: <IssuesPage /> },
              { path: "issues/new", element: <ReportIssuePage /> },
              { path: "issues/queue", element: <IssuesPage queue />, handle: { wide: true } },
              { path: "issues/:issueId", element: <IssuePage /> },
            ],
          },
          { path: "notifications", element: <NotificationsPage /> },
          { path: "join", element: <JoinPage /> },
          { path: "account", element: <AccountPage /> },
          {
            path: "platform",
            element: <PlatformLayout />,
            handle: { wide: true },
            children: [
              { index: true, element: <Navigate to="colleges" replace /> },
              { path: "colleges", element: <CollegesTab /> },
              { path: "colleges/:collegeId", element: <CollegeDetailPage /> },
              { path: "users", element: <UsersTab /> },
              { path: "audit", element: <PlatformAuditTab /> },
            ],
          },
          {
            path: "manage",
            element: <ManageLayout />,
            handle: { wide: true },
            children: [
              { index: true, element: <Navigate to="requests" replace /> },
              { path: "requests", element: <RequestsTab /> },
              { path: "members", element: <MembersTab /> },
              { path: "academics", element: <RequireCapability needs="manage_academics"><AcademicsAdminTab /></RequireCapability> },
              { path: "academics/sections/:sectionId", element: <RequireCapability needs="manage_academics"><SectionSetupPage /></RequireCapability> },
              { path: "moderation", element: <RequireCapability needs="moderate_community"><ModerationTab /></RequireCapability> },
              { path: "invites", element: <RequireCapability needs="manage_college"><InvitesTab /></RequireCapability> },
              { path: "departments", element: <RequireCapability needs="manage_college"><DepartmentsTab /></RequireCapability> },
              { path: "roster", element: <RequireCapability needs="manage_college"><RosterTab /></RequireCapability> },
              { path: "audit", element: <RequireCapability needs="manage_college"><AuditTab /></RequireCapability> },
            ],
          },
        ],
      },
    ],
  },
];
