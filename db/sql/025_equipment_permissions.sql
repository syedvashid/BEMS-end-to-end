-- 025: equipment permissions and role mapping. Run as bems_owner.
insert into permissions (code, module, description) values
  ('equipment.view','equipment','View equipment'),
  ('equipment.add','equipment','Register equipment'),
  ('equipment.change','equipment','Edit equipment'),
  ('equipment.delete','equipment','Delete equipment'),
  ('equipment.import','equipment','Import equipment from file'),
  ('equipment.transition','equipment','Lifecycle steps, operational state and moves')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (values
    ('SYSTEM_ADMIN','equipment.view'),('SYSTEM_ADMIN','equipment.add'),('SYSTEM_ADMIN','equipment.change'),
    ('SYSTEM_ADMIN','equipment.delete'),('SYSTEM_ADMIN','equipment.import'),('SYSTEM_ADMIN','equipment.transition'),
    ('BIOMED_ADMIN','equipment.view'),('BIOMED_ADMIN','equipment.add'),('BIOMED_ADMIN','equipment.change'),
    ('BIOMED_ADMIN','equipment.delete'),('BIOMED_ADMIN','equipment.import'),('BIOMED_ADMIN','equipment.transition'),
    ('BIOMED_ENGINEER','equipment.view'),('BIOMED_ENGINEER','equipment.add'),
    ('BIOMED_ENGINEER','equipment.change'),('BIOMED_ENGINEER','equipment.transition'),
    ('STORE_OFFICER','equipment.view'),('STORE_OFFICER','equipment.add'),
    ('FINANCE','equipment.view'),('DEPARTMENT_USER','equipment.view'),('AUDITOR','equipment.view')
  ) m (role_code, perm_code)
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('025', 'equipment permissions') on conflict (version) do nothing;
