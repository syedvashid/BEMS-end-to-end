begin;

create table if not exists equipment_usage_logs (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  allocation_id bigint,
  department_id bigint,
  started_at timestamptz not null,
  ended_at timestamptz not null,
  duration_minutes numeric(12,2) generated always as
    (round((extract(epoch from (ended_at - started_at)) / 60.0)::numeric, 2)) stored,
  operator_name text,
  patient_reference text,
  encounter_reference text,
  procedure_text text,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_usage_logs_public_id unique (public_id),
  constraint ck_equipment_usage_logs_rowver check (row_version >= 1),
  constraint fk_usage_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_usage_allocation foreign key (facility_id, allocation_id)
    references equipment_allocations (facility_id, id),
  constraint fk_usage_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint ck_usage_window check (ended_at >= started_at and ended_at - started_at <= interval '30 days'),
  constraint ck_usage_patient_ref check (patient_reference is null or patient_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_usage_encounter_ref check (encounter_reference is null or encounter_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_usage_text_len check (coalesce(length(operator_name), 0) <= 200
    and coalesce(length(procedure_text), 0) <= 500 and coalesce(length(notes), 0) <= 2000),
  constraint ex_usage_no_overlap exclude using gist (
    facility_id with =, equipment_id with =, tstzrange(started_at, ended_at, '[)') with &&)
    where (is_active)
);

create index if not exists ix_usage_equipment_started
  on equipment_usage_logs (facility_id, equipment_id, started_at desc);
create index if not exists ix_usage_department_started
  on equipment_usage_logs (facility_id, department_id, started_at desc);

drop trigger if exists trg_equipment_usage_logs_touch on equipment_usage_logs;
create trigger trg_equipment_usage_logs_touch before update on equipment_usage_logs
  for each row execute function touch_row();

grant select, insert, update on equipment_usage_logs to bems_app;

insert into schema_version (version, description)
  values ('041', 'equipment_usage_logs') on conflict (version) do nothing;
commit;