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
import MapPage from './pages/MapPage'
import SettingsPage from './pages/SettingsPage'
// ERP modules
import ERPDashboardPage from './pages/ERPDashboardPage'
import CustomersPage from './pages/CustomersPage'
import CustomerDetailPage from './pages/CustomerDetailPage'
import QuotesPage from './pages/QuotesPage'
import QuoteDetailPage from './pages/QuoteDetailPage'
import ContractsPage from './pages/ContractsPage'
import InvoicesPage from './pages/InvoicesPage'
import InventoryPage from './pages/InventoryPage'
import LeadsPage from './pages/LeadsPage'
import ReportsPage from './pages/ReportsPage'
import CustomFieldsPage from './pages/CustomFieldsPage'
import RolesPage from './pages/RolesPage'

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
                  {/* Field service */}
                  <Route path="/elevators" element={<ElevatorsPage />} />
                  <Route path="/elevators/:id" element={<ElevatorDetailPage />} />
                  <Route path="/calls" element={<CallsPage />} />
                  <Route path="/pending-calls" element={<PendingCallsPage />} />
                  <Route path="/technicians" element={<TechniciansPage />} />
                  <Route path="/maintenance" element={<MaintenancePage />} />
                  <Route path="/inspections" element={<InspectionsPage />} />
                  <Route path="/management-companies" element={<ManagementCompaniesPage />} />
                  <Route path="/map" element={<MapPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/import" element={<ImportPage />} />
                  {/* ERP */}
                  <Route path="/erp" element={<ERPDashboardPage />} />
                  <Route path="/customers" element={<CustomersPage />} />
                  <Route path="/customers/:id" element={<CustomerDetailPage />} />
                  <Route path="/quotes" element={<QuotesPage />} />
                  <Route path="/quotes/:id" element={<QuoteDetailPage />} />
                  <Route path="/contracts" element={<ContractsPage />} />
                  <Route path="/contracts/:id" element={<ContractsPage />} />
                  <Route path="/invoices" element={<InvoicesPage />} />
                  <Route path="/invoices/:id" element={<InvoicesPage />} />
                  <Route path="/inventory" element={<InventoryPage />} />
                  <Route path="/leads" element={<LeadsPage />} />
                  {/* Reports & Settings */}
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/custom-fields" element={<CustomFieldsPage />} />
                  <Route path="/roles" element={<RolesPage />} />
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
