-- 066: charge permissions and role mapping (run as bems_owner)
insert into permissions (code, module, description) values
  ('charge.view',      'charge', 'View charge items, mappings, charge records, previews and billing reports'),
  ('charge.configure', 'charge', 'Manage charge items, charge mappings and charge settings'),
  ('charge.approve',   'charge', 'Approve, cancel, reverse, recalculate and export charge records')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (values
    ('SYSTEM_ADMIN','charge.view'), ('SYSTEM_ADMIN','charge.configure'), ('SYSTEM_ADMIN','charge.approve'),
    ('BIOMED_ADMIN','charge.view'), ('BIOMED_ADMIN','charge.configure'), ('BIOMED_ADMIN','charge.approve'),
    ('FINANCE','charge.view'),      ('FINANCE','charge.configure'),      ('FINANCE','charge.approve'),
    ('BIOMED_ENGINEER','charge.view'),
    ('AUDITOR','charge.view')
  ) m (role_code, perm_code)
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('066', 'charge permissions') on conflict (version) do nothing;
