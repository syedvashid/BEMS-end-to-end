insert into permissions (code, module, description) values
  ('calibration.view','calibration','View calibration schedules and records'),
  ('calibration.manage','calibration','Create, change and delete calibration schedules; generate schedules'),
  ('calibration.record','calibration','Record a calibration result'),
  ('calibration.review','calibration','Review the impact of a failed calibration'),
  ('warranty.view','warranty','View warranties and claims'),
  ('warranty.add','warranty','Add warranties and claims'),
  ('warranty.change','warranty','Change warranties and claims'),
  ('warranty.delete','warranty','Delete warranties and claims'),
  ('amc.view','amc','View AMC/CMC contracts'),
  ('amc.add','amc','Add and renew AMC/CMC contracts'),
  ('amc.change','amc','Change AMC/CMC contracts and coverage'),
  ('amc.delete','amc','Delete AMC/CMC contracts'),
  ('licence.view','licence','View equipment licences'),
  ('licence.add','licence','Add and renew equipment licences'),
  ('licence.change','licence','Change equipment licences'),
  ('licence.delete','licence','Delete equipment licences')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
from (
  select role_code, perm_code
  from (values ('SYSTEM_ADMIN'), ('BIOMED_ADMIN')) a (role_code)
  cross join (values
    ('calibration.view'),('calibration.manage'),('calibration.record'),('calibration.review'),
    ('warranty.view'),('warranty.add'),('warranty.change'),('warranty.delete'),
    ('amc.view'),('amc.add'),('amc.change'),('amc.delete'),
    ('licence.view'),('licence.add'),('licence.change'),('licence.delete')) b (perm_code)
  union all select * from (values
    ('BIOMED_ENGINEER','calibration.view'),('BIOMED_ENGINEER','calibration.manage'),('BIOMED_ENGINEER','calibration.record'),
    ('BIOMED_ENGINEER','warranty.view'),('BIOMED_ENGINEER','warranty.add'),('BIOMED_ENGINEER','warranty.change'),
    ('BIOMED_ENGINEER','amc.view'),('BIOMED_ENGINEER','amc.add'),('BIOMED_ENGINEER','amc.change'),
    ('BIOMED_ENGINEER','licence.view'),('BIOMED_ENGINEER','licence.add'),('BIOMED_ENGINEER','licence.change'),
    ('STORE_OFFICER','warranty.view'),('STORE_OFFICER','warranty.add'),('STORE_OFFICER','warranty.change'),
    ('STORE_OFFICER','calibration.view'),('STORE_OFFICER','amc.view'),('STORE_OFFICER','licence.view'),
    ('FINANCE','calibration.view'),('FINANCE','warranty.view'),('FINANCE','amc.view'),('FINANCE','licence.view'),
    ('DEPARTMENT_USER','calibration.view'),
    ('AUDITOR','calibration.view'),('AUDITOR','warranty.view'),('AUDITOR','amc.view'),('AUDITOR','licence.view')
  ) x (role_code, perm_code)
) m
join roles r on r.code = m.role_code and r.is_active
join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description) values ('037', 'compliance permissions and role mapping')
  on conflict (version) do nothing;