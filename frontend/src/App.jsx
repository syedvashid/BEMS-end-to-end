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
// import VendorsPage from './pages/VendorsPage.jsx'
import DocumentsPage from './pages/DocumentsPage.jsx'

import EquipmentPage from './pages/EquipmentPage.jsx'
import EquipmentBulkPage from './pages/EquipmentBulkPage.jsx'
import EquipmentImportPage from './pages/EquipmentImportPage.jsx'
import EquipmentDetailPage from './pages/EquipmentDetailPage.jsx'
import WorkOrdersPage from './pages/WorkOrdersPage.jsx'
import WorkOrderDetailPage from './pages/WorkOrderDetailPage.jsx'
import PmDuePage from './pages/PmDuePage.jsx'
import MaintenancePlansPage from './pages/MaintenancePlansPage.jsx'
import ChecklistTemplatesPage from './pages/ChecklistTemplatesPage.jsx'
import SparePartsPage from './pages/SparePartsPage.jsx'
import CalibrationPage from './pages/CalibrationPage.jsx'
import WarrantiesPage from './pages/WarrantiesPage.jsx'
import AmcContractsPage from './pages/AmcContractsPage.jsx'
import LicencesPage from './pages/LicencesPage.jsx'
import CompliancePage from './pages/CompliancePage.jsx'
console.log('App module loaded')
const guard = (code, element) => (
  <PermissionGate code={code} fallback={<AccessDeniedPage />}>{element}</PermissionGate>
)

export default function App() {
  console.log('App module loaded')
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
         <Route path="documents" element={guard('document.view', <DocumentsPage />)} />
          <Route path="equipment" element={guard('equipment.view', <EquipmentPage />)} />
        <Route path="equipment/bulk" element={guard('equipment.add', <EquipmentBulkPage />)} />
        <Route path="equipment/import" element={guard('equipment.import', <EquipmentImportPage />)} />
        <Route path="equipment/:publicId" element={guard('equipment.view', <EquipmentDetailPage />)} />
        <Route path="work-orders" element={guard('work_order.view', <WorkOrdersPage />)} />
        <Route path="work-orders/:publicId" element={guard('work_order.view', <WorkOrderDetailPage />)} />
        <Route path="pm-due" element={guard('maintenance_plan.view', <PmDuePage />)} />
        <Route path="maintenance-plans" element={guard('maintenance_plan.view', <MaintenancePlansPage />)} />
        <Route path="checklist-templates" element={guard('checklist_template.view', <ChecklistTemplatesPage />)} />
        <Route path="spare-parts" element={guard('spare_part.view', <SparePartsPage />)} />
        <Route path="calibration" element={guard('calibration.view', <CalibrationPage />)} />
        <Route path="warranties" element={guard('warranty.view', <WarrantiesPage />)} />
        <Route path="amc-contracts" element={guard('amc.view', <AmcContractsPage />)} />
        <Route path="licences" element={guard('licence.view', <LicencesPage />)} />
        <Route path="compliance" element={guard('calibration.view', <CompliancePage />)} />
      </Route>
    </Routes>
  )
}