begin;

insert into permissions (code, module, description) values
  ('allocation.view',     'allocation',  'View equipment allocations and availability'),
  ('allocation.assign',   'allocation',  'Allocate and release equipment'),
  ('allocation.override', 'allocation',  'Override the calibration gate on allocation'),
  ('reservation.view',    'reservation', 'View reservations'),
  ('reservation.add',     'reservation', 'Create and cancel own reservations'),
  ('reservation.manage',  'reservation', 'Manage all reservations and any department'),
  ('usage.view',          'usage',       'View usage logs'),
  ('usage.add',           'usage',       'Add usage logs'),
  ('usage.change',        'usage',       'Edit usage logs'),
  ('usage.delete',        'usage',       'Delete usage logs'),
  ('transfer.view',       'transfer',    'View transfer requests'),
  ('transfer.request',    'transfer',    'Request equipment transfers'),
  ('transfer.approve',    'transfer',    'Approve or reject equipment transfers')
on conflict (code) do nothing;

with all13 (arr) as (values (array[
  'allocation.view','allocation.assign','allocation.override',
  'reservation.view','reservation.add','reservation.manage',
  'usage.view','usage.add','usage.change','usage.delete',
  'transfer.view','transfer.request','transfer.approve']::text[])),
m (role_code, perm_code) as (
  select r, unnest(a.arr) from all13 a cross join unnest(array['SYSTEM_ADMIN','BIOMED_ADMIN']) r
  union all select 'BIOMED_ENGINEER', unnest(array[
    'allocation.view','allocation.assign','reservation.view','reservation.add','reservation.manage',
    'usage.view','usage.add','usage.change','transfer.view','transfer.request','transfer.approve'])
  union all select 'STORE_OFFICER', unnest(array[
    'allocation.view','reservation.view','usage.view','transfer.view'])
  union all select 'DEPARTMENT_USER', unnest(array[
    'allocation.view','reservation.view','reservation.add','usage.view','transfer.view','transfer.request'])
  union all select r, unnest(array['allocation.view','reservation.view','usage.view','transfer.view'])
    from unnest(array['FINANCE','AUDITOR']) r
)
insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from m
  join roles r on r.code = m.role_code and r.is_active
  join permissions p on p.code = m.perm_code
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('044', 'allocation, reservation, usage, transfer permissions') on conflict (version) do nothing;
commit;