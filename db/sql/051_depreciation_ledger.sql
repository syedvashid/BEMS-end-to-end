-- 051 depreciation runs and entries (run as bems_owner)
begin;

create table if not exists depreciation_runs (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  run_period date not null,
  status text not null default 'RUNNING',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  assets_processed integer not null default 0,
  entries_created integer not null default 0,
  skipped_no_policy integer not null default 0,
  skipped_no_cost integer not null default 0,
  skipped_no_start_date integer not null default 0,
  total_charge numeric(14,2) not null default 0,
  triggered_by_system boolean not null default false,
  error_message text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_depreciation_runs_public_id unique (public_id),
  constraint uq_depreciation_runs_facility_id_id unique (facility_id, id),
  constraint ck_depreciation_runs_rowver check (row_version >= 1),
  constraint ck_depreciation_runs_period check (extract(day from run_period) = 1),
  constraint ck_depreciation_runs_status check (status in ('RUNNING','COMPLETED','FAILED'))
);
create index if not exists ix_depreciation_runs_facility_started on depreciation_runs (facility_id, started_at desc);
drop trigger if exists trg_depreciation_runs_touch on depreciation_runs;
create trigger trg_depreciation_runs_touch before update on depreciation_runs
  for each row execute function touch_row();
grant select, insert, update on depreciation_runs to bems_app;

create table if not exists depreciation_entries (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  period_month date not null,
  entry_type text not null,
  opening_value numeric(14,2) not null,
  charge numeric(14,2) not null,
  closing_value numeric(14,2) not null,
  method text,
  policy_id bigint,
  run_id bigint,
  days_charged integer,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_depreciation_entries_public_id unique (public_id),
  constraint uq_depreciation_entries_equipment_month unique (equipment_id, period_month),
  constraint fk_depreciation_entries_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_depreciation_entries_policy foreign key (facility_id, policy_id)
    references depreciation_policies (facility_id, id),
  constraint fk_depreciation_entries_run foreign key (facility_id, run_id)
    references depreciation_runs (facility_id, id),
  constraint ck_depreciation_entries_month check (extract(day from period_month) = 1),
  constraint ck_depreciation_entries_type check (entry_type in ('REGULAR','OPENING_BALANCE','DISPOSAL_STUB')),
  constraint ck_depreciation_entries_values check (opening_value >= 0 and charge >= 0 and closing_value >= 0),
  constraint ck_depreciation_entries_math check (closing_value = opening_value - charge),
  constraint ck_depreciation_entries_opening_zero check (entry_type <> 'OPENING_BALANCE' or charge = 0),
  constraint ck_depreciation_entries_days check (days_charged is null or days_charged between 0 and 31)
);
create index if not exists ix_depreciation_entries_facility_month on depreciation_entries (facility_id, period_month);
create index if not exists ix_depreciation_entries_run on depreciation_entries (run_id);
grant select, insert on depreciation_entries to bems_app;

insert into schema_version (version, description)
  values ('051', 'depreciation runs and entries') on conflict (version) do nothing;
commit;
