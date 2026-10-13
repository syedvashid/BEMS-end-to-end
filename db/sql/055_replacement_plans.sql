-- 055 replacement plans (run as bems_owner)
begin;

create table if not exists replacement_plans (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  planned_year smallint not null,
  estimated_cost numeric(14,2),
  priority text not null default 'MEDIUM',
  status text not null default 'CANDIDATE',
  justification text,
  replaced_by_equipment_id bigint,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_replacement_plans_public_id unique (public_id),
  constraint ck_replacement_plans_rowver check (row_version >= 1),
  constraint fk_replacement_plans_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_replacement_plans_replaced_by foreign key (facility_id, replaced_by_equipment_id)
    references equipment (facility_id, id),
  constraint ck_replacement_plans_year check (planned_year between 2000 and 2200),
  constraint ck_replacement_plans_cost check (estimated_cost is null or estimated_cost >= 0),
  constraint ck_replacement_plans_priority check (priority in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_replacement_plans_status check (status in ('CANDIDATE','APPROVED_FOR_BUDGET','DEFERRED','COMPLETED','CANCELLED')),
  constraint ck_replacement_plans_not_self check (replaced_by_equipment_id is null or replaced_by_equipment_id <> equipment_id)
);
create unique index if not exists ux_replacement_plans_equipment_open_active
  on replacement_plans (facility_id, equipment_id)
  where status in ('CANDIDATE','APPROVED_FOR_BUDGET','DEFERRED') and is_active;
create index if not exists ix_replacement_plans_year on replacement_plans (facility_id, planned_year, status);
drop trigger if exists trg_replacement_plans_touch on replacement_plans;
create trigger trg_replacement_plans_touch before update on replacement_plans
  for each row execute function touch_row();
grant select, insert, update on replacement_plans to bems_app;

insert into schema_version (version, description)
  values ('055', 'replacement plans') on conflict (version) do nothing;
commit;
