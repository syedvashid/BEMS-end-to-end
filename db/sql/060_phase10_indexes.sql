create index if not exists ix_p10_wo_pm_due
  on work_orders (facility_id, work_order_type, due_date) where work_order_type = 'PREVENTIVE';
create index if not exists ix_p10_wo_bd_reported
  on work_orders (facility_id, work_order_type, reported_at) where work_order_type = 'BREAKDOWN';
create index if not exists ix_p10_wo_completed
  on work_orders (facility_id, completed_at);
create index if not exists ix_p10_holds_equipment_started
  on equipment_holds (facility_id, equipment_id, started_at);
create index if not exists ix_p10_usage_started
  on equipment_usage_logs (facility_id, started_at);
create index if not exists ix_p10_alloc_assigned
  on equipment_allocations (facility_id, assigned_at);
create index if not exists ix_p10_stock_created
  on spare_part_stock_entries (facility_id, created_at);
create index if not exists ix_p10_audit_entity_time
  on audit_log (facility_id, entity_type, occurred_at desc);
create index if not exists ix_p10_equipment_stage_dept
  on equipment (facility_id, lifecycle_stage, owning_department_id);

insert into schema_version (version, description)
  values ('060', 'phase 10 performance indexes') on conflict (version) do nothing;