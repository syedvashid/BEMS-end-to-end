insert into permissions (code, module, description) values
  ('report.view',   'report', 'View and run reports on screen'),
  ('report.export', 'report', 'Export reports to CSV, Excel and PDF and download them'),
  ('stats.run',     'stats',  'Rebuild the daily statistics'),
  ('audit.verify',  'audit',  'Verify the audit hash chain')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (values
    ('SYSTEM_ADMIN','report.view'), ('BIOMED_ADMIN','report.view'), ('BIOMED_ENGINEER','report.view'),
    ('STORE_OFFICER','report.view'), ('FINANCE','report.view'), ('AUDITOR','report.view'),
    ('SYSTEM_ADMIN','report.export'), ('BIOMED_ADMIN','report.export'), ('BIOMED_ENGINEER','report.export'),
    ('FINANCE','report.export'), ('AUDITOR','report.export'),
    ('SYSTEM_ADMIN','stats.run'), ('BIOMED_ADMIN','stats.run'),
    ('SYSTEM_ADMIN','audit.verify'), ('BIOMED_ADMIN','audit.verify'), ('AUDITOR','audit.verify')
  ) m (role_code, perm_code)
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('061', 'report, stats and audit.verify permissions') on conflict (version) do nothing;