import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAdmin } from './auth/RequireAdmin'
import { RequireUser } from './auth/RequireUser'
import { RoleRedirect } from './auth/RoleRedirect'
import { SelectViewPage } from './auth/SelectViewPage'
import { AdminLayout } from './admin/layouts/AdminLayout'
import { RequireAuth } from './auth/RequireAuth'
import { MainLayout } from './layouts/MainLayout'
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
const ExperimentsPage = lazy(() =>
  import('./pages/ExperimentsPage').then((m) => ({
    default: m.ExperimentsPage,
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
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const PrivacyPage = lazy(() =>
  import('./pages/PrivacyPage').then((m) => ({ default: m.PrivacyPage })),
)
const AdminIntegrationsPage = lazy(() =>
  import('./admin/pages/AdminIntegrationsPage').then((m) => ({
    default: m.AdminIntegrationsPage,
  })),
)

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/authorization/callback" element={<CallbackPage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route element={<RequireAuth />}>
        {/* Role decides the landing surface: admin console vs user app. */}
        <Route path="/" element={<RoleRedirect />} />
        <Route path="/administration" element={<RoleRedirect />} />
        <Route path="/select-view" element={<SelectViewPage />} />

        <Route element={<RequireUser />}>
          <Route element={<MainLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/agent-builder" element={<AgentBuilderPage />} />
            <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/agent-store" element={<AgentStorePage />} />
            <Route path="/workflow-store" element={<WorkflowStorePage />} />
            <Route path="/scheduled-jobs" element={<ScheduledJobsPage />} />
            <Route path="/usage" element={<UsagePage />} />
            <Route path="/insights" element={<InsightsPage />} />
            <Route path="/experiments" element={<ExperimentsPage />} />
            <Route path="/evaluations" element={<EvaluationsPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
            <Route path="/agent-skills" element={<AgentSkillsPage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
          </Route>
        </Route>

        <Route element={<RequireAdmin />}>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="mcp-tools" replace />} />
            <Route path="mcp-tools" element={<AdminIntegrationsPage />} />
            <Route path="mcp-tools/:server" element={<AdminIntegrationsPage />} />
            <Route
              path="integrations"
              element={<Navigate to="/admin/mcp-tools" replace />}
            />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
