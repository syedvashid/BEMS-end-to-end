-- 027_maintenance_plans.sql  (run as bems_owner)
create table if not exists maintenance_plans (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  name text not null,
  equipment_id bigint not null,
  checklist_template_id bigint,
  frequency_type text not null,
  frequency_value integer not null,
  lead_days integer not null default 7,
  priority text not null default 'MEDIUM',
  default_assignee_user_id bigint references users (id),
  start_date date not null,
  last_performed_date date,
  next_due_date date not null,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_maintenance_plans_public_id unique (public_id),
  constraint uq_maintenance_plans_facility_id_id unique (facility_id, id),
  constraint ck_maintenance_plans_rowver check (row_version >= 1),
  constraint ck_maintenance_plans_name check (btrim(name) <> ''),
  constraint ck_maintenance_plans_freq_type check (frequency_type in ('DAYS','MONTHS')),
  constraint ck_maintenance_plans_freq_value check (frequency_value > 0),
  constraint ck_maintenance_plans_lead check (lead_days >= 0),
  constraint ck_maintenance_plans_priority check (priority in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint fk_maintenance_plans_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_maintenance_plans_template foreign key (facility_id, checklist_template_id)
    references checklist_templates (facility_id, id)
);
create unique index if not exists ux_maintenance_plans_equipment_name_active
  on maintenance_plans (facility_id, equipment_id, lower(name)) where is_active;
create index if not exists ix_maintenance_plans_due on maintenance_plans (facility_id, next_due_date) where is_active;
create index if not exists ix_maintenance_plans_template on maintenance_plans (facility_id, checklist_template_id);
drop trigger if exists trg_maintenance_plans_touch on maintenance_plans;
create trigger trg_maintenance_plans_touch before update on maintenance_plans
  for each row execute function touch_row();
grant select, insert, update on maintenance_plans to bems_app;

insert into schema_version (version, description)
  values ('027', 'maintenance_plans') on conflict (version) do nothing;
