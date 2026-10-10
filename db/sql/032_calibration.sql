-- Same-facility keys needed by Phase 6 composite FKs (idempotent)
do $$
declare t text; fid int2; iid int2;
begin
  foreach t in array array['equipment','vendors','work_orders'] loop
    select attnum into fid from pg_attribute where attrelid = t::regclass and attname = 'facility_id' and not attisdropped;
    select attnum into iid from pg_attribute where attrelid = t::regclass and attname = 'id' and not attisdropped;
    if not exists (
      select 1 from pg_index i
      where i.indrelid = t::regclass and i.indisunique and i.indpred is null and i.indexprs is null
        and i.indnkeyatts = 2 and i.indnatts = 2 and i.indkey::int2[] @> array[fid, iid]
    ) then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id');
    end if;
  end loop;
end $$;

create table if not exists calibration_schedules (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  frequency_type text not null,
  frequency_value integer not null,
  lead_days integer not null default 30,
  last_calibrated_date date,
  next_due_date date not null,
  on_fail_hold_equipment boolean not null default true,
  on_fail_open_work_order boolean not null default true,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_calibration_schedules_public_id unique (public_id),
  constraint uq_calibration_schedules_facility_id unique (facility_id, id),
  constraint ck_calibration_schedules_rowver check (row_version >= 1),
  constraint ck_calibration_schedules_freq_type check (frequency_type in ('DAYS','MONTHS')),
  constraint ck_calibration_schedules_freq_value check (frequency_value > 0),
  constraint ck_calibration_schedules_lead check (lead_days >= 0),
  constraint fk_calibration_schedules_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id)
);
create unique index if not exists ux_calibration_schedules_equipment_active
  on calibration_schedules (facility_id, equipment_id) where is_active;
create index if not exists ix_calibration_schedules_due
  on calibration_schedules (facility_id, next_due_date) where is_active;
drop trigger if exists trg_calibration_schedules_touch on calibration_schedules;
create trigger trg_calibration_schedules_touch before update on calibration_schedules
  for each row execute function touch_row();
grant select, insert, update on calibration_schedules to bems_app;

create table if not exists calibration_records (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  calibration_schedule_id bigint not null,
  performed_date date not null,
  calibration_reason text not null,
  performed_by_type text not null,
  performer_vendor_id bigint,
  performer_name text,
  reference_standard_details text,
  certificate_number text,
  result text not null,
  readings jsonb not null default '[]'::jsonb,
  deviation_summary text,
  next_due_date date not null,
  notes text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_calibration_records_public_id unique (public_id),
  constraint uq_calibration_records_facility_id unique (facility_id, id),
  constraint ck_calibration_records_reason check (calibration_reason in ('SCHEDULED','POST_REPAIR','AFTER_FAILURE','OTHER')),
  constraint ck_calibration_records_by_type check (performed_by_type in ('IN_HOUSE','VENDOR','ACCREDITED_LAB')),
  constraint ck_calibration_records_result check (result in ('PASS','FAIL')),
  constraint ck_calibration_records_readings check (jsonb_typeof(readings) = 'array' and jsonb_array_length(readings) <= 50),
  constraint ck_calibration_records_next_due check (next_due_date > performed_date),
  constraint ck_calibration_records_performer check (
    performer_vendor_id is not null or nullif(btrim(coalesce(performer_name, '')), '') is not null),
  constraint fk_calibration_records_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_calibration_records_schedule foreign key (facility_id, calibration_schedule_id)
    references calibration_schedules (facility_id, id),
  constraint fk_calibration_records_vendor foreign key (facility_id, performer_vendor_id)
    references vendors (facility_id, id)
);
create index if not exists ix_calibration_records_equipment
  on calibration_records (equipment_id, performed_date desc);
create index if not exists ix_calibration_records_schedule
  on calibration_records (facility_id, calibration_schedule_id);
grant select, insert on calibration_records to bems_app;

create table if not exists calibration_impact_reviews (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  calibration_record_id bigint not null,
  review_notes text not null,
  patient_impact_found boolean not null,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_calibration_impact_reviews_public_id unique (public_id),
  constraint uq_calibration_impact_reviews_record unique (calibration_record_id),
  constraint ck_calibration_impact_reviews_notes check (btrim(review_notes) <> ''),
  constraint fk_calibration_impact_reviews_record foreign key (facility_id, calibration_record_id)
    references calibration_records (facility_id, id)
);
grant select, insert on calibration_impact_reviews to bems_app;

insert into schema_version (version, description) values ('032', 'calibration schedules, records, impact reviews')
  on conflict (version) do nothing;