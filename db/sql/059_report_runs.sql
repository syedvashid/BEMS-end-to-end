create table if not exists report_runs (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  report_code varchar(50) not null,
  report_name varchar(150) not null,
  parameters jsonb not null default '{}'::jsonb,
  format varchar(10) not null,
  status varchar(10) not null default 'QUEUED',
  row_count integer,
  original_filename varchar(255),
  storage_key varchar(100),
  file_size_bytes bigint,
  sha256 char(64),
  error_message varchar(300),
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_report_runs_public_id unique (public_id),
  constraint ck_report_runs_rowver check (row_version >= 1),
  constraint ck_report_runs_params check (jsonb_typeof(parameters) = 'object'),
  constraint ck_report_runs_format check (format in ('CSV', 'XLSX', 'PDF')),
  constraint ck_report_runs_status check (status in ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'EXPIRED')),
  constraint ck_report_runs_rows check (row_count is null or row_count >= 0),
  constraint ck_report_runs_size check (file_size_bytes is null or file_size_bytes >= 0),
  constraint ck_report_runs_sha check (sha256 is null or sha256 ~ '^[0-9a-f]{64}$'),
  constraint ck_report_runs_completed_file check (status <> 'COMPLETED' or storage_key is not null)
);
create unique index if not exists ux_report_runs_storage_key
  on report_runs (storage_key) where storage_key is not null;
create index if not exists ix_report_runs_requester
  on report_runs (facility_id, created_by, requested_at desc);
create index if not exists ix_report_runs_queued
  on report_runs (status) where status = 'QUEUED';

drop trigger if exists trg_report_runs_touch on report_runs;
create trigger trg_report_runs_touch before update on report_runs
  for each row execute function touch_row();

grant select, insert, update on report_runs to bems_app;

insert into schema_version (version, description)
  values ('059', 'report_runs') on conflict (version) do nothing;