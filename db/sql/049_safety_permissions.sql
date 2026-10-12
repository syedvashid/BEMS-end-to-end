-- 049 safety permissions and role mapping. Run as bems_owner.
begin;

insert into permissions (code, module, description) values
  ('incident.view','incident','View equipment incidents'),
  ('incident.add','incident','Report equipment incidents'),
  ('incident.manage','incident','Investigate, close and manage incidents'),
  ('recall.view','recall','View recall notices'),
  ('recall.add','recall','Create recall notices'),
  ('recall.manage','recall','Edit, resolve units, close and cancel recall notices'),
  ('verification.view','verification','View physical verifications'),
  ('verification.add','verification','Create, start and scan physical verifications'),
  ('verification.manage','verification','Complete, cancel and reconcile physical verifications')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from (
    select rc.role_code, pc.perm_code
      from (values ('SYSTEM_ADMIN'),('BIOMED_ADMIN'),('BIOMED_ENGINEER')) rc (role_code)
     cross join (values ('incident.view'),('incident.add'),('incident.manage'),
                        ('recall.view'),('recall.add'),('recall.manage'),
                        ('verification.view'),('verification.add'),('verification.manage')) pc (perm_code)
    union all
    select * from (values
      ('STORE_OFFICER','incident.view'),('STORE_OFFICER','incident.add'),('STORE_OFFICER','recall.view'),
      ('STORE_OFFICER','verification.view'),('STORE_OFFICER','verification.add'),
      ('DEPARTMENT_USER','incident.view'),('DEPARTMENT_USER','incident.add'),
      ('FINANCE','verification.view'),('FINANCE','verification.add'),
      ('AUDITOR','incident.view'),('AUDITOR','recall.view'),('AUDITOR','verification.view')
    ) x (role_code, perm_code)
  ) m
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description) values ('049', 'safety permissions') on conflict (version) do nothing;
commit;
