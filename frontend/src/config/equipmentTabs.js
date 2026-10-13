// One array drives the equipment detail tabs. A later phase plugs in by adding `component`
// to its entry: component receives { equipment, reload }.
import EquipmentSafetyTab from '../components/safety/EquipmentSafetyTab'
import EquipmentFinanceTab from '../components/finance/EquipmentFinanceTab'
export const EQUIPMENT_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'installation', label: 'Installation & Acceptance' },
  { key: 'status', label: 'Status history' },
  { key: 'movements', label: 'Movement history' },
  { key: 'documents', label: 'Documents' },
  { key: 'qr', label: 'QR & Labels' },
  { key: 'maintenance', label: 'Maintenance', phase: 5 },
  { key: 'calibration', label: 'Calibration', phase: 6 },
  { key: 'contracts', label: 'Contracts & Warranty', phase: 6 },
  { key: 'assignments', label: 'Assignments', phase: 7 },
  { key: 'usage', label: 'Usage', phase: 7 },
  { key: 'safety', label: 'Safety', component: EquipmentSafetyTab },
    { key: 'finance', label: 'Finance', component: EquipmentFinanceTab },
]


