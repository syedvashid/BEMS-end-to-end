-- 056 finance, condemnation and disposal permissions (run as bems_owner)
begin;

insert into permissions (code, module, description) values
  ('finance.view','finance','View book values, depreciation, TCO, finance summary and replacement planning'),
  ('finance.manage','finance','Manage depreciation policies, finance settings, opening book values and replacement plans'),
  ('finance.run','finance','Run depreciation and generate TCO snapshots'),
  ('condemnation.view','condemnation','View condemnation requests'),
  ('condemnation.add','condemnation','Request condemnation'),
  ('condemnation.approve','condemnation','Approve, reject or revoke condemnation'),
  ('disposal.view','disposal','View disposals'),
  ('disposal.manage','disposal','Create, edit, complete and cancel disposals')
on conflict (code) do nothing;

with m (role_code, perms) as (values
  ('SYSTEM_ADMIN',   array['finance.view','finance.manage','finance.run','condemnation.view','condemnation.add','condemnation.approve','disposal.view','disposal.manage']::text[]),
  ('BIOMED_ADMIN',   array['finance.view','finance.manage','finance.run','condemnation.view','condemnation.add','condemnation.approve','disposal.view','disposal.manage']::text[]),
  ('BIOMED_ENGINEER',array['finance.view','condemnation.view','condemnation.add','disposal.view','disposal.manage']::text[]),
  ('STORE_OFFICER',  array['condemnation.view','disposal.view','disposal.manage']::text[]),
  ('FINANCE',        array['finance.view','finance.manage','finance.run','condemnation.view','disposal.view','disposal.manage']::text[]),
  ('AUDITOR',        array['finance.view','condemnation.view','disposal.view']::text[])
)
insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from m
  cross join lateral unnest(m.perms) as u (perm_code)
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = u.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('056', 'finance condemnation disposal permissions') on conflict (version) do nothing;
commit;
