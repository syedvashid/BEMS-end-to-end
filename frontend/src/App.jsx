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
import AvailabilityPage from './pages/AvailabilityPage.jsx'
import AllocationsPage from './pages/AllocationsPage.jsx'
import BedsidePage from './pages/BedsidePage.jsx'
import ReservationsPage from './pages/ReservationsPage.jsx'
import TransfersPage from './pages/TransfersPage.jsx'
import UsageLogsPage from './pages/UsageLogsPage.jsx'
import IncidentsPage from './pages/IncidentsPage.jsx'
import IncidentDetailPage from './pages/IncidentDetailPage.jsx'
import RecallsPage from './pages/RecallsPage.jsx'
import RecallDetailPage from './pages/RecallDetailPage.jsx'
import VerificationsPage from './pages/VerificationsPage.jsx'
import VerificationRunPage from './pages/VerificationRunPage.jsx'
import FinanceSummaryPage from './pages/FinanceSummaryPage.jsx'
import DepreciationPoliciesPage from './pages/DepreciationPoliciesPage.jsx'
import CondemnationPage from './pages/CondemnationPage.jsx'
import CondemnationDetailPage from './pages/CondemnationDetailPage.jsx'
import DisposalsPage from './pages/DisposalsPage.jsx'
import ReplacementPlanningPage from './pages/ReplacementPlanningPage.jsx'

import DashboardsPage from './pages/DashboardsPage.jsx'
import DowntimePage from './pages/DowntimePage.jsx'
import UtilizationPage from './pages/UtilizationPage.jsx'
import ReportCenterPage from './pages/ReportCenterPage.jsx'
import AuditTrailPage from './pages/AuditTrailPage.jsx'
import ChargeItemsPage from './pages/ChargeItemsPage.jsx'
import ChargeMappingsPage from './pages/ChargeMappingsPage.jsx'
import ChargeRecordsPage from './pages/ChargeRecordsPage.jsx'
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
        <Route path="audit-log" element={guard('audit.view', <AuditTrailPage />)} />
        
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
        <Route path="availability" element={guard('allocation.view', <AvailabilityPage />)} />
        <Route path="allocations" element={guard('allocation.view', <AllocationsPage />)} />
        <Route path="bedside" element={guard('allocation.view', <BedsidePage />)} />
        <Route path="reservations" element={guard('reservation.view', <ReservationsPage />)} />
        <Route path="transfers" element={guard('transfer.view', <TransfersPage />)} />
        <Route path="usage-logs" element={guard('usage.view', <UsageLogsPage />)} />
        <Route path="incidents" element={guard('incident.view', <IncidentsPage />)} />
        <Route path="incidents/:publicId" element={guard('incident.view', <IncidentDetailPage />)} />
        <Route path="recall-notices" element={guard('recall.view', <RecallsPage />)} />
        <Route path="recall-notices/:publicId" element={guard('recall.view', <RecallDetailPage />)} />
        <Route path="verifications" element={guard('verification.view', <VerificationsPage />)} />
        <Route path="verifications/:publicId" element={guard('verification.view', <VerificationRunPage />)} />
                <Route path="verifications/:publicId" element={guard('verification.view', <VerificationRunPage />)} />
        <Route path="finance" element={guard('finance.view', <FinanceSummaryPage />)} />
        <Route path="depreciation-policies" element={guard('finance.view', <DepreciationPoliciesPage />)} />
        <Route path="condemnation" element={guard('condemnation.view', <CondemnationPage />)} />
        <Route path="condemnation/:publicId" element={guard('condemnation.view', <CondemnationDetailPage />)} />
        <Route path="disposals" element={guard('disposal.view', <DisposalsPage />)} />
        <Route path="replacement-planning" element={guard('finance.view', <ReplacementPlanningPage />)} />
                <Route path="dashboards" element={<DashboardsPage />} />
        <Route path="dashboards/:name" element={<DashboardsPage />} />
        <Route path="reports" element={guard('report.view', <ReportCenterPage />)} />
        <Route path="downtime" element={guard('equipment.view', <DowntimePage />)} />
        <Route path="utilization" element={guard('usage.view', <UtilizationPage />)} />
         <Route path="charge-items" element={guard('charge.view', <ChargeItemsPage />)} />
        <Route path="charge-mappings" element={guard('charge.view', <ChargeMappingsPage />)} />
        <Route path="charge-records" element={guard('charge.view', <ChargeRecordsPage />)} />
      </Route>
    </Routes>
  )
}