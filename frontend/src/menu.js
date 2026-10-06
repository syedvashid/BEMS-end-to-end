export const MENU = [
  { to: '/facilities', label: 'Facilities', permission: 'facility.view' },
  { to: '/users', label: 'Users', permission: 'user.view' },
  { to: '/roles', label: 'Roles', permission: 'role.view' },
  { to: '/audit-log', label: 'Audit Log', permission: 'audit.view' },

  // phase 2
  // { to: '/roles', label: 'Roles', permission: 'role.view' },
  { to: '/departments', label: 'Departments', permission: 'department.view' },
  { to: '/locations', label: 'Locations', permission: 'location.view' },
  { to: '/equipment-categories', label: 'Equipment Categories', permission: 'equipment_category.view' },
  { to: '/vendors', label: 'Vendors', permission: 'vendor.view' },
  { to: '/funding-sources', label: 'Funding Sources', permission: 'funding_source.view' },
  { to: '/equipment-models', label: 'Equipment Models', permission: 'equipment_model.view' },
]