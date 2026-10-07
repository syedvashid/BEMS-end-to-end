insert into permissions (code, module, description) values
  ('document.view','document','View documents'),
  ('document.add','document','Upload documents'),
  ('document.change','document','Edit documents and add versions'),
  ('document.delete','document','Delete documents')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (values
    ('SYSTEM_ADMIN','document.view'),('SYSTEM_ADMIN','document.add'),('SYSTEM_ADMIN','document.change'),('SYSTEM_ADMIN','document.delete'),
    ('BIOMED_ADMIN','document.view'),('BIOMED_ADMIN','document.add'),('BIOMED_ADMIN','document.change'),('BIOMED_ADMIN','document.delete'),
    ('BIOMED_ENGINEER','document.view'),('BIOMED_ENGINEER','document.add'),('BIOMED_ENGINEER','document.change'),
    ('STORE_OFFICER','document.view'),('STORE_OFFICER','document.add'),
    ('FINANCE','document.view'),
    ('DEPARTMENT_USER','document.view'),
    ('AUDITOR','document.view')
  ) m (role_code, perm_code)
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('020', 'document permissions') on conflict (version) do nothing;