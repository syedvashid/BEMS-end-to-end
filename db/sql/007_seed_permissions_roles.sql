insert into permissions (code, module, description) values
    ('facility.view',   'facility', 'View facilities'),
    ('facility.add',    'facility', 'Create facilities'),
    ('facility.change', 'facility', 'Edit facilities'),
    ('facility.delete', 'facility', 'Deactivate facilities'),
    ('user.view',       'user',     'View users'),
    ('user.add',        'user',     'Create users'),
    ('user.change',     'user',     'Edit users and facility-role assignments'),
    ('user.delete',     'user',     'Deactivate users'),
    ('role.view',       'role',     'View roles and permissions'),
    ('role.manage',     'role',     'Create/edit custom roles and their permissions'),
    ('audit.view',      'audit',    'View the audit log')
on conflict (code) do nothing;

insert into roles (code, name, description, is_system) values
    ('SYSTEM_ADMIN',    'System Administrator', 'Full access to foundation data',          true),
    ('BIOMED_ADMIN',    'Biomedical Admin',     'Runs the biomedical department',          true),
    ('BIOMED_ENGINEER', 'Biomedical Engineer',  'Hands-on equipment engineer',             true),
    ('STORE_OFFICER',   'Store Officer',        'Stores and receiving',                    true),
    ('DEPARTMENT_USER', 'Department User',      'Clinical or support department user',     true),
    ('FINANCE',         'Finance',              'Finance and accounts',                    true),
    ('AUDITOR',         'Auditor',              'Read-only, including the audit log',      true)
on conflict (code) where is_active do nothing;

-- SYSTEM_ADMIN gets everything
insert into role_permissions (role_id, permission_id)
select r.id, p.id from roles r cross join permissions p
 where r.code = 'SYSTEM_ADMIN' and r.is_active
on conflict (role_id, permission_id) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (values
    ('BIOMED_ADMIN',    'facility.view'),
    ('BIOMED_ADMIN',    'facility.change'),
    ('BIOMED_ADMIN',    'user.view'),
    ('BIOMED_ADMIN',    'user.add'),
    ('BIOMED_ADMIN',    'user.change'),
    ('BIOMED_ADMIN',    'role.view'),
    ('BIOMED_ADMIN',    'audit.view'),
    ('BIOMED_ENGINEER', 'facility.view'),
    ('STORE_OFFICER',   'facility.view'),
    ('DEPARTMENT_USER', 'facility.view'),
    ('FINANCE',         'facility.view'),
    ('AUDITOR',         'facility.view'),
    ('AUDITOR',         'user.view'),
    ('AUDITOR',         'role.view'),
    ('AUDITOR',         'audit.view')
  ) m (role_code, perm_code)
  join roles r       on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
values ('007', 'seed permissions, system roles, role mapping')
on conflict (version) do nothing;