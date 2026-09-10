import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { MainLayout } from './layouts/MainLayout'
import { InsightsPage } from './pages/InsightsPage'
import { KnowledgeBasesPage } from './pages/KnowledgeBasesPage'
import { UsagePage } from './pages/UsagePage'
import { AgentBuilderPage } from './pages/AgentBuilderPage'
import { AgentStorePage } from './pages/AgentStorePage'
import { CallbackPage } from './pages/CallbackPage'
import { ChatPage } from './pages/ChatPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { LogoutPage } from './pages/LogoutPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ScheduledJobsPage } from './pages/ScheduledJobsPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { SettingsPage } from './pages/SettingsPage'
import { ToolsPage } from './pages/ToolsPage'
import { WorkflowBuilderPage } from './pages/WorkflowBuilderPage'
import { WorkflowStorePage } from './pages/WorkflowStorePage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/authorization/callback" element={<CallbackPage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/agent-builder" element={<AgentBuilderPage />} />
          <Route path="/workflow-builder" element={<WorkflowBuilderPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agent-store" element={<AgentStorePage />} />
          <Route path="/workflow-store" element={<WorkflowStorePage />} />
          <Route path="/scheduled-jobs" element={<ScheduledJobsPage />} />
          <Route path="/usage" element={<UsagePage />} />
          <Route path="/administration" element={<Navigate to="/usage" replace />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
