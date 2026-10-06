import { Navigate, Route, Routes } from 'react-router-dom'
import PermissionGate from './components/PermissionGate.jsx'
import AppLayout from './layouts/AppLayout.jsx'
import AccessDeniedPage from './pages/AccessDeniedPage.jsx'
import AuditLogPage from './pages/AuditLogPage.jsx'
import FacilitiesPage from './pages/FacilitiesPage.jsx'
import HealthPage from './pages/HealthPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import RoleDetailPage from './pages/RoleDetailPage.jsx'
import RolesPage from './pages/RolesPage.jsx'
import UsersPage from './pages/UsersPage.jsx'

// import AuditLogPage from './pages/AuditLogPage.jsx'
import DepartmentsPage from './pages/DepartmentsPage.jsx'
import EquipmentCategoriesPage from './pages/EquipmentCategoriesPage.jsx'
import EquipmentModelsPage from './pages/EquipmentModelsPage.jsx'
// import FacilitiesPage from './pages/FacilitiesPage.jsx'
import FundingSourcesPage from './pages/FundingSourcesPage.jsx'
import LocationsPage from './pages/LocationsPage.jsx'
import VendorsPage from './pages/VendorsPage.jsx'

const guard = (code, element) => (
  <PermissionGate code={code} fallback={<AccessDeniedPage />}>{element}</PermissionGate>
)

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/facilities" replace />} />
        <Route path="facilities" element={guard('facility.view', <FacilitiesPage />)} />
        <Route path="users" element={guard('user.view', <UsersPage />)} />
        <Route path="roles" element={guard('role.view', <RolesPage />)} />
        <Route path="roles/:publicId" element={guard('role.view', <RoleDetailPage />)} />
        <Route path="audit-log" element={guard('audit.view', <AuditLogPage />)} />
        <Route path="health" element={<HealthPage />} />
        <Route path="*" element={<NotFoundPage />} />
          //phase 2
        {/* <Route path="roles/:publicId" element={guard('role.view', <RoleDetailPage />)} /> */}
        <Route path="departments" element={guard('department.view', <DepartmentsPage />)} />
        <Route path="locations" element={guard('location.view', <LocationsPage />)} />
        <Route path="equipment-categories" element={guard('equipment_category.view', <EquipmentCategoriesPage />)} />
        <Route path="vendors" element={guard('vendor.view', <VendorsPage />)} />
        <Route path="funding-sources" element={guard('funding_source.view', <FundingSourcesPage />)} />
        <Route path="equipment-models" element={guard('equipment_model.view', <EquipmentModelsPage />)} />
      </Route>
    </Routes>
  )
}