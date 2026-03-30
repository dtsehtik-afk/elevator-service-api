import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import Shell from './components/layout/Shell'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ElevatorsPage from './pages/ElevatorsPage'
import ElevatorDetailPage from './pages/ElevatorDetailPage'
import CallsPage from './pages/CallsPage'
import TechniciansPage from './pages/TechniciansPage'
import MaintenancePage from './pages/MaintenancePage'

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <AuthGuard>
              <Shell>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/elevators" element={<ElevatorsPage />} />
                  <Route path="/elevators/:id" element={<ElevatorDetailPage />} />
                  <Route path="/calls" element={<CallsPage />} />
                  <Route path="/technicians" element={<TechniciansPage />} />
                  <Route path="/maintenance" element={<MaintenancePage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Shell>
            </AuthGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
