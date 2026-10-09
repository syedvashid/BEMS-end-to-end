-- 031_maintenance_permissions.sql  (run as bems_owner)
insert into permissions (code, module, description) values
  ('checklist_template.view','checklist_template','View checklist templates'),
  ('checklist_template.add','checklist_template','Add checklist templates'),
  ('checklist_template.change','checklist_template','Change checklist templates'),
  ('checklist_template.delete','checklist_template','Delete checklist templates'),
  ('maintenance_plan.view','maintenance_plan','View maintenance plans'),
  ('maintenance_plan.add','maintenance_plan','Add or generate maintenance plans'),
  ('maintenance_plan.change','maintenance_plan','Change maintenance plans'),
  ('maintenance_plan.delete','maintenance_plan','Delete maintenance plans'),
  ('work_order.view','work_order','View work orders'),
  ('work_order.add','work_order','Report a breakdown'),
  ('work_order.change','work_order','Create other work orders and edit fields'),
  ('work_order.assign','work_order','Assign work orders'),
  ('work_order.execute','work_order','Start, resume, complete, checklist, parts, notes'),
  ('work_order.close','work_order','Close and cancel work orders'),
  ('spare_part.view','spare_part','View spare parts'),
  ('spare_part.add','spare_part','Add spare parts'),
  ('spare_part.change','spare_part','Change spare parts'),
  ('spare_part.delete','spare_part','Delete spare parts'),
  ('spare_part.stock','spare_part','Receive and adjust stock')
on conflict (code) do nothing;

insert into role_permissions (role_id, permission_id)
select r.id, p.id
  from roles r
  join permissions p on p.code in (
    'checklist_template.view','checklist_template.add','checklist_template.change','checklist_template.delete',
    'maintenance_plan.view','maintenance_plan.add','maintenance_plan.change','maintenance_plan.delete',
    'work_order.view','work_order.add','work_order.change','work_order.assign','work_order.execute','work_order.close',
    'spare_part.view','spare_part.add','spare_part.change','spare_part.delete','spare_part.stock')
 where r.is_active and (
       r.code in ('SYSTEM_ADMIN','BIOMED_ADMIN')
    or (r.code = 'BIOMED_ENGINEER' and p.code in (
          'checklist_template.view','checklist_template.add','checklist_template.change',
          'maintenance_plan.view','maintenance_plan.add','maintenance_plan.change',
          'work_order.view','work_order.add','work_order.change','work_order.assign','work_order.execute','work_order.close',
          'spare_part.view','spare_part.add','spare_part.change'))
    or (r.code = 'STORE_OFFICER' and p.code in (
          'spare_part.view','spare_part.add','spare_part.change','spare_part.stock',
          'work_order.view','checklist_template.view','maintenance_plan.view'))
    or (r.code = 'DEPARTMENT_USER' and p.code in ('work_order.view','work_order.add'))
    or (r.code in ('FINANCE','AUDITOR') and p.code in (
          'checklist_template.view','maintenance_plan.view','work_order.view','spare_part.view')))
on conflict (role_id, permission_id) do nothing;

insert into schema_version (version, description)
  values ('031', 'maintenance permissions and role mapping') on conflict (version) do nothing;
