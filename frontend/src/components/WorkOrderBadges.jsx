import { PRIORITY_LABEL, STATUS_LABEL } from '../utils/maintenance'
import '../styles/maintenance.css'

export const StatusPill = ({ status }) => (
  <span className={`mt-pill mt-s-${status}`}>{STATUS_LABEL[status] || status}</span>
)
export const PriorityPill = ({ priority }) => (
  <span className={`mt-pill mt-p-${priority}`}>{PRIORITY_LABEL[priority] || priority}</span>
)
export const OverdueBadge = ({ show }) => (show ? <span className="mt-pill mt-overdue">Overdue</span> : null)
