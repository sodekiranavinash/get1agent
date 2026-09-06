import { Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth/RequireAuth'
import { MainLayout } from './layouts/MainLayout'
import { CallbackPage } from './pages/CallbackPage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { LogoutPage } from './pages/LogoutPage'
import { NotFoundPage } from './pages/NotFoundPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/authorization/callback" element={<CallbackPage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<MainLayout />}>
          <Route path="/" element={<HomePage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
