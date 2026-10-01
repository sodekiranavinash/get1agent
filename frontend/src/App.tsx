import { lazy, useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAdmin } from './auth/RequireAdmin'
import { RequireUser } from './auth/RequireUser'
import { RoleRedirect } from './auth/RoleRedirect'
import { SelectViewPage } from './auth/SelectViewPage'
import { AdminLayout } from './admin/layouts/AdminLayout'
import { RequireAuth } from './auth/RequireAuth'
import { AppFooter } from './components/layout/AppFooter'
import { MainLayout } from './layouts/MainLayout'
import { AdaptiveLayout } from './layouts/AdaptiveLayout'
import { CallbackPage } from './pages/CallbackPage'
import { LoginPage } from './pages/LoginPage'
import { LogoutPage } from './pages/LogoutPage'
import { NotFoundPage } from './pages/NotFoundPage'

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const AgentBuilderPage = lazy(() =>
  import('./pages/AgentBuilderPage').then((m) => ({ default: m.AgentBuilderPage })),
)
const WorkflowBuilderPage = lazy(() =>
  import('./pages/WorkflowBuilderPage').then((m) => ({
    default: m.WorkflowBuilderPage,
  })),
)
const ChatPage = lazy(() =>
  import('./pages/ChatPage').then((m) => ({ default: m.ChatPage })),
)
const AgentStorePage = lazy(() =>
  import('./pages/AgentStorePage').then((m) => ({ default: m.AgentStorePage })),
)
const WorkflowStorePage = lazy(() =>
  import('./pages/WorkflowStorePage').then((m) => ({
    default: m.WorkflowStorePage,
  })),
)
const ScheduledJobsPage = lazy(() =>
  import('./pages/ScheduledJobsPage').then((m) => ({
    default: m.ScheduledJobsPage,
  })),
)
const UsagePage = lazy(() =>
  import('./pages/UsagePage').then((m) => ({ default: m.UsagePage })),
)
const InsightsPage = lazy(() =>
  import('./pages/InsightsPage').then((m) => ({ default: m.InsightsPage })),
)
const TracesPage = lazy(() =>
  import('./pages/TracesPage').then((m) => ({ default: m.TracesPage })),
)
const ExperimentsPage = lazy(() =>
  import('./pages/ExperimentsPage').then((m) => ({
    default: m.ExperimentsPage,
  })),
)
const PlaygroundPage = lazy(() =>
  import('./pages/PlaygroundPage').then((m) => ({
    default: m.PlaygroundPage,
  })),
)
const EvaluationsPage = lazy(() =>
  import('./pages/EvaluationsPage').then((m) => ({
    default: m.EvaluationsPage,
  })),
)
const MetricsPage = lazy(() =>
  import('./pages/MetricsPage').then((m) => ({ default: m.MetricsPage })),
)
const KnowledgeBasesPage = lazy(() =>
  import('./pages/KnowledgeBasesPage').then((m) => ({
    default: m.KnowledgeBasesPage,
  })),
)
const AgentSkillsPage = lazy(() =>
  import('./pages/AgentSkillsPage').then((m) => ({
    default: m.AgentSkillsPage,
  })),
)
const ToolsPage = lazy(() =>
  import('./pages/ToolsPage').then((m) => ({ default: m.ToolsPage })),
)
const StoragePage = lazy(() =>
  import('./pages/StoragePage').then((m) => ({ default: m.StoragePage })),
)
const VaultPage = lazy(() =>
  import('./pages/VaultPage').then((m) => ({ default: m.VaultPage })),
)
const McpOAuthCallbackPage = lazy(() =>
  import('./pages/McpOAuthCallbackPage').then((m) => ({
    default: m.McpOAuthCallbackPage,
  })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const PrivacyPage = lazy(() =>
  import('./pages/PrivacyPage').then((m) => ({ default: m.PrivacyPage })),
)
const DocumentationPage = lazy(() =>
  import('./pages/DocumentationPage').then((m) => ({
    default: m.DocumentationPage,
  })),
)
const ChangelogPage = lazy(() =>
  import('./pages/ChangelogPage').then((m) => ({ default: m.ChangelogPage })),
)
const StatusPage = lazy(() =>
  import('./pages/StatusPage').then((m) => ({ default: m.StatusPage })),
)
const SupportPage = lazy(() =>
  import('./pages/SupportPage').then((m) => ({ default: m.SupportPage })),
)
const TermsPage = lazy(() =>
  import('./pages/TermsPage').then((m) => ({ default: m.TermsPage })),
)
const SecurityPage = lazy(() =>
  import('./pages/SecurityPage').then((m) => ({ default: m.SecurityPage })),
)
const AdminIntegrationsPage = lazy(() =>
  import('./admin/pages/AdminIntegrationsPage').then((m) => ({
    default: m.AdminIntegrationsPage,
  })),
)
const AdminUsersPage = lazy(() =>
  import('./admin/pages/AdminUsersPage').then((m) => ({
    default: m.AdminUsersPage,
  })),
)
const AdminSupportPage = lazy(() =>
  import('./admin/pages/AdminSupportPage').then((m) => ({
    default: m.AdminSupportPage,
  })),
)
const AdminSecurityPage = lazy(() =>
  import('./admin/pages/AdminSecurityPage').then((m) => ({
    default: m.AdminSecurityPage,
  })),
)

/**
 * Warms the lazy route chunks once the browser is idle, so navigating to a
 * page never waits on a chunk download — the page mounts instantly and only
 * the API-driven skeleton can appear.
 */
function PrefetchRoutes() {
  useEffect(() => {
    const prefetch = () => {
      void import('./pages/DashboardPage')
      void import('./pages/AgentBuilderPage')
      void import('./pages/WorkflowBuilderPage')
      void import('./pages/ChatPage')
      void import('./pages/AgentStorePage')
      void import('./pages/WorkflowStorePage')
      void import('./pages/ScheduledJobsPage')
      void import('./pages/UsagePage')
      void import('./pages/InsightsPage')
      void import('./pages/TracesPage')
      void import('./pages/ExperimentsPage')
      void import('./pages/PlaygroundPage')
      void import('./pages/EvaluationsPage')
      void import('./pages/MetricsPage')
      void import('./pages/KnowledgeBasesPage')
      void import('./pages/AgentSkillsPage')
      void import('./pages/ToolsPage')
      void import('./pages/StoragePage')
      void import('./pages/VaultPage')
      void import('./pages/SettingsPage')
      void import('./pages/PrivacyPage')
      void import('./pages/DocumentationPage')
      void import('./pages/ChangelogPage')
      void import('./pages/StatusPage')
      void import('./pages/SupportPage')
      void import('./pages/TermsPage')
      void import('./pages/SecurityPage')
      void import('./admin/pages/AdminIntegrationsPage')
      void import('./admin/pages/AdminUsersPage')
      void import('./admin/pages/AdminSupportPage')
      void import('./admin/pages/AdminSecurityPage')
    }
    const win = window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number
      cancelIdleCallback?: (id: number) => void
    }
    if (win.requestIdleCallback) {
      const id = win.requestIdleCallback(prefetch, { timeout: 3000 })
      return () => win.cancelIdleCallback?.(id)
    }
    const timer = window.setTimeout(prefetch, 2000)
    return () => window.clearTimeout(timer)
  }, [])
  return null
}

function App() {
  return (
    <>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/authorization/callback" element={<CallbackPage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route element={<RequireAuth />}>
        {/* Role decides the landing surface: admin console vs user app. */}
        <Route path="/" element={<RoleRedirect />} />
        <Route path="/administration" element={<RoleRedirect />} />
        <Route path="/select-view" element={<SelectViewPage />} />
        <Route path="/mcp/callback" element={<McpOAuthCallbackPage />} />

        <Route element={<RequireUser />}>
          <Route element={<MainLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/agent-builder" element={<AgentBuilderPage />} />
            <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/conversation/:conversationId" element={<ChatPage />} />
            <Route path="/agent-store" element={<AgentStorePage />} />
            <Route path="/workflow-store" element={<WorkflowStorePage />} />
            <Route path="/scheduled-jobs" element={<ScheduledJobsPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/traces" element={<TracesPage />} />
            <Route path="/mcp-builder" element={<ExperimentsPage />} />
            <Route path="/playground" element={<PlaygroundPage />} />
            <Route path="/evaluations" element={<EvaluationsPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
            <Route path="/agent-skills" element={<AgentSkillsPage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/storage" element={<StoragePage />} />
            <Route path="/vault" element={<VaultPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route element={<RequireAdmin />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="mcp-tools" replace />} />
            <Route path="mcp-tools" element={<AdminIntegrationsPage />} />
            <Route path="mcp-tools/:server" element={<AdminIntegrationsPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="support" element={<AdminSupportPage />} />
            <Route path="security-reports" element={<AdminSecurityPage />} />
            <Route
              path="integrations"
              element={<Navigate to="/admin/mcp-tools" replace />}
            />
          </Route>
        </Route>
      </Route>
      {/* Footer pages keep the app sidebar when signed in, and work from the
          sign-in screen too. */}
      <Route element={<AdaptiveLayout />}>
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/docs" element={<DocumentationPage />} />
        <Route path="/changelog" element={<ChangelogPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/security" element={<SecurityPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    <AppFooter />
    <PrefetchRoutes />
    </>
  )
}

export default App
