insert into permissions (code, module, description)
select m.module || '.' || a.action, m.module, a.label || ' ' || m.label
from (values
  ('department','departments'), ('location','locations'),
  ('equipment_category','equipment categories'), ('vendor','vendors and contacts'),
  ('funding_source','funding sources'), ('equipment_model','equipment models')
) m (module, label)
cross join (values ('view','View'), ('add','Add'), ('change','Change'), ('delete','Delete')) a (action, label)
on conflict (code) do nothing;

with mods (module) as (
  values ('department'), ('location'), ('equipment_category'), ('vendor'), ('funding_source'), ('equipment_model')
),
acts (action) as (values ('view'), ('add'), ('change'), ('delete')),
g (role_code, module, action) as (
  select r.c, m.module, a.action
    from (values ('SYSTEM_ADMIN'), ('BIOMED_ADMIN')) r (c), mods m, acts a
  union all
  select r.c, m.module, 'view'
    from (values ('BIOMED_ENGINEER'), ('STORE_OFFICER'), ('FINANCE'), ('AUDITOR')) r (c), mods m
  union all
  select * from (values
    ('BIOMED_ENGINEER','equipment_model','add'), ('BIOMED_ENGINEER','equipment_model','change'),
    ('BIOMED_ENGINEER','vendor','add'),          ('BIOMED_ENGINEER','vendor','change'),
    ('STORE_OFFICER','vendor','add'),            ('STORE_OFFICER','vendor','change'),
    ('FINANCE','funding_source','add'),          ('FINANCE','funding_source','change'),
    ('DEPARTMENT_USER','department','view'),     ('DEPARTMENT_USER','location','view'),
    ('DEPARTMENT_USER','equipment_category','view'), ('DEPARTMENT_USER','equipment_model','view')
  ) x (role_code, module, action)
)
insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from g
  join roles r on r.code = g.role_code and r.is_active
  join permissions p on p.code = g.module || '.' || g.action
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('017', 'phase 2 permissions and role mapping') on conflict (version) do nothing;