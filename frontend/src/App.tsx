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
import TechAppPage from './pages/TechAppPage'
import InspectionsPage from './pages/InspectionsPage'
import PendingCallsPage from './pages/PendingCallsPage'
import ManagementCompaniesPage from './pages/ManagementCompaniesPage'
import ImportPage from './pages/ImportPage'

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const userRole = useAuthStore((s) => s.userRole)
  if (!token) return <Navigate to="/login" replace />
  if (userRole === 'TECHNICIAN') return <Navigate to="/tech" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/tech" element={<TechAppPage />} />
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
                  <Route path="/inspections" element={<InspectionsPage />} />
                  <Route path="/pending-calls" element={<PendingCallsPage />} />
                  <Route path="/management-companies" element={<ManagementCompaniesPage />} />
                  <Route path="/import" element={<ImportPage />} />
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
