-- 028_work_orders.sql  (run as bems_owner)
create table if not exists work_orders (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  wo_number text not null,
  work_order_type text not null,
  priority text not null default 'MEDIUM',
  status text not null default 'OPEN',
  equipment_id bigint not null,
  maintenance_plan_id bigint,
  parent_work_order_id bigint,
  due_date date,
  problem_description text,
  reported_at timestamptz not null default now(),
  reported_by_name text,
  reported_by_department_id bigint,
  equipment_unusable boolean not null default false,
  assigned_to_user_id bigint references users (id),
  assigned_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  closed_at timestamptz,
  closed_by bigint references users (id),
  signoff_name text,
  root_cause text,
  action_taken text,
  labour_cost numeric(14,2),
  vendor_cost numeric(14,2),
  coverage_source text,
  service_provider_vendor_id bigint,
  vendor_call_reference text,
  vendor_engineer_name text,
  vendor_visit_at timestamptz,
  standby_equipment_id bigint,
  downtime_start timestamptz,
  downtime_end timestamptz,
  cancel_reason text,
  status_note text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_work_orders_public_id unique (public_id),
  constraint uq_work_orders_facility_id_id unique (facility_id, id),
  constraint uq_work_orders_number unique (facility_id, wo_number),
  constraint ck_work_orders_rowver check (row_version >= 1),
  constraint ck_work_orders_number check (wo_number ~ '^WO-[0-9]{4}-[0-9]{6}$'),
  constraint ck_work_orders_type check (work_order_type in ('PREVENTIVE','BREAKDOWN','CORRECTIVE')),
  constraint ck_work_orders_priority check (priority in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_work_orders_status check (status in ('OPEN','ASSIGNED','IN_PROGRESS','WAITING_PARTS','COMPLETED','CLOSED','CANCELLED')),
  constraint ck_work_orders_pm_due check (work_order_type <> 'PREVENTIVE' or due_date is not null),
  constraint ck_work_orders_bd_problem check (work_order_type <> 'BREAKDOWN' or (problem_description is not null and btrim(problem_description) <> '')),
  constraint ck_work_orders_labour check (labour_cost is null or labour_cost >= 0),
  constraint ck_work_orders_vendor_cost check (vendor_cost is null or vendor_cost >= 0),
  constraint ck_work_orders_coverage check (coverage_source is null or coverage_source in ('WARRANTY','AMC','PAID','IN_HOUSE')),
  constraint ck_work_orders_downtime check (downtime_end is null or downtime_start is null or downtime_end >= downtime_start),
  constraint ck_work_orders_not_own_parent check (parent_work_order_id is distinct from id),
  constraint ck_work_orders_standby check (standby_equipment_id is distinct from equipment_id),
  constraint fk_work_orders_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_work_orders_plan foreign key (facility_id, maintenance_plan_id) references maintenance_plans (facility_id, id),
  constraint fk_work_orders_parent foreign key (facility_id, parent_work_order_id) references work_orders (facility_id, id),
  constraint fk_work_orders_department foreign key (facility_id, reported_by_department_id) references departments (facility_id, id),
  constraint fk_work_orders_provider foreign key (facility_id, service_provider_vendor_id) references vendors (facility_id, id),
  constraint fk_work_orders_standby foreign key (facility_id, standby_equipment_id) references equipment (facility_id, id)
);
create unique index if not exists ux_work_orders_plan_due
  on work_orders (maintenance_plan_id, due_date)
  where work_order_type = 'PREVENTIVE' and maintenance_plan_id is not null;
create index if not exists ix_work_orders_status on work_orders (facility_id, status);
create index if not exists ix_work_orders_equipment on work_orders (facility_id, equipment_id);
create index if not exists ix_work_orders_assignee on work_orders (facility_id, assigned_to_user_id);
create index if not exists ix_work_orders_due on work_orders (facility_id, due_date);
drop trigger if exists trg_work_orders_touch on work_orders;
create trigger trg_work_orders_touch before update on work_orders
  for each row execute function touch_row();

create table if not exists work_order_transitions (
  from_status text not null,
  to_status text not null,
  primary key (from_status, to_status)
);
insert into work_order_transitions (from_status, to_status) values
  ('OPEN','ASSIGNED'), ('OPEN','IN_PROGRESS'), ('OPEN','CANCELLED'),
  ('ASSIGNED','IN_PROGRESS'), ('ASSIGNED','OPEN'), ('ASSIGNED','CANCELLED'),
  ('IN_PROGRESS','WAITING_PARTS'), ('IN_PROGRESS','COMPLETED'), ('IN_PROGRESS','CANCELLED'),
  ('WAITING_PARTS','IN_PROGRESS'), ('WAITING_PARTS','CANCELLED'),
  ('COMPLETED','CLOSED')
on conflict do nothing;
grant select on work_order_transitions to bems_app;

create or replace function work_orders_status_guard() returns trigger
language plpgsql as $$
begin
  if new.status is distinct from old.status
     and not exists (select 1 from work_order_transitions t
                      where t.from_status = old.status and t.to_status = new.status) then
    raise exception 'work order status change % -> % is not allowed', old.status, new.status
      using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists trg_work_orders_status_guard on work_orders;
create trigger trg_work_orders_status_guard before update on work_orders
  for each row execute function work_orders_status_guard();
grant select, insert, update on work_orders to bems_app;

create table if not exists work_order_events (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  work_order_id bigint not null,
  event_type text not null,
  from_status text,
  to_status text,
  note text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_work_order_events_public_id unique (public_id),
  constraint ck_work_order_events_type check (event_type in
    ('CREATED','ASSIGNED','STARTED','WAITING_PARTS','RESUMED','COMPLETED','CLOSED','CANCELLED','PART_ISSUED','PART_RETURNED','NOTE')),
  constraint fk_work_order_events_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id)
);
create index if not exists ix_work_order_events_wo on work_order_events (work_order_id, created_at);
grant select, insert on work_order_events to bems_app;

create table if not exists work_order_checklist_items (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  work_order_id bigint not null,
  sequence integer not null,
  item_text text not null,
  item_type text not null,
  unit text,
  min_value numeric(14,4),
  max_value numeric(14,4),
  result text,
  measured_value numeric(14,4),
  remarks text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_wo_checklist_items_public_id unique (public_id),
  constraint uq_wo_checklist_items_seq unique (work_order_id, sequence),
  constraint ck_wo_checklist_items_rowver check (row_version >= 1),
  constraint ck_wo_checklist_items_seq check (sequence > 0),
  constraint ck_wo_checklist_items_type check (item_type in ('CHECK','MEASUREMENT')),
  constraint ck_wo_checklist_items_result check (result is null or result in ('PASS','FAIL','NA')),
  constraint ck_wo_checklist_items_range check (min_value is null or max_value is null or min_value <= max_value),
  constraint fk_wo_checklist_items_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id)
);
drop trigger if exists trg_wo_checklist_items_touch on work_order_checklist_items;
create trigger trg_wo_checklist_items_touch before update on work_order_checklist_items
  for each row execute function touch_row();
grant select, insert, update on work_order_checklist_items to bems_app;

insert into schema_version (version, description)
  values ('028', 'work_orders, transitions + trigger, events, checklist snapshot') on conflict (version) do nothing;
