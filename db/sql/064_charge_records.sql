-- 064: charge_records with the immutability trigger (run as bems_owner)
create table if not exists charge_records (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  record_number varchar(30) not null,
  idempotency_key text not null,
  record_type varchar(10) not null default 'CHARGE',
  source_type varchar(15) not null,
  allocation_id bigint,
  usage_log_id bigint,
  equipment_id bigint not null,
  charge_mapping_id bigint not null,
  charge_item_id bigint not null,
  billing_rule varchar(20) not null,
  basis varchar(15) not null,
  unit_label varchar(30) not null,
  unit_rate numeric(14,2) not null,
  quantity numeric(10,2) not null,
  amount numeric(14,2) not null,
  period_key text not null,
  period_start timestamptz,
  period_end timestamptz,
  charge_date date not null,
  patient_reference text not null,
  encounter_reference text,
  department_id bigint,
  calculation jsonb not null default '{}'::jsonb,
  status varchar(20) not null default 'PENDING_REVIEW',
  approved_by bigint references users (id),
  approved_at timestamptz,
  cancelled_by bigint references users (id),
  cancelled_at timestamptz,
  cancel_reason text,
  reverses_record_id bigint,
  reversal_reason text,
  corrects_record_id bigint,
  exported_at timestamptz,
  exported_by bigint references users (id),
  export_reference text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_charge_records_public_id unique (public_id),
  constraint uq_charge_records_facility_id unique (facility_id, id),
  constraint uq_charge_records_number unique (facility_id, record_number),
  constraint uq_charge_records_idem unique (facility_id, idempotency_key),
  constraint ck_charge_records_rowver check (row_version >= 1),
  constraint fk_charge_records_allocation foreign key (facility_id, allocation_id) references equipment_allocations (facility_id, id),
  constraint fk_charge_records_usage foreign key (facility_id, usage_log_id) references equipment_usage_logs (facility_id, id),
  constraint fk_charge_records_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_charge_records_mapping foreign key (facility_id, charge_mapping_id) references charge_mappings (facility_id, id),
  constraint fk_charge_records_item foreign key (facility_id, charge_item_id) references charge_items (facility_id, id),
  constraint fk_charge_records_department foreign key (facility_id, department_id) references departments (facility_id, id),
  constraint fk_charge_records_reverses foreign key (facility_id, reverses_record_id) references charge_records (facility_id, id),
  constraint fk_charge_records_corrects foreign key (facility_id, corrects_record_id) references charge_records (facility_id, id),
  constraint ck_charge_records_number_fmt check (record_number ~ '^CHG-[0-9]{4}-[0-9]{6}$'),
  constraint ck_charge_records_key check (btrim(idempotency_key) <> '' and char_length(idempotency_key) <= 250),
  constraint ck_charge_records_type check (record_type in ('CHARGE','REVERSAL')),
  constraint ck_charge_records_source check (source_type in ('ALLOCATION','USAGE_LOG')),
  constraint ck_charge_records_source_link check (
       (source_type = 'ALLOCATION' and allocation_id is not null and usage_log_id is null)
    or (source_type = 'USAGE_LOG' and usage_log_id is not null and allocation_id is null)),
  constraint ck_charge_records_rule check (billing_rule in ('HOURLY','DAILY','PER_USE','PER_SESSION','PER_ADMISSION')),
  constraint ck_charge_records_basis check (basis in ('ALLOCATION','USAGE_LOG')),
  constraint ck_charge_records_rate check (unit_rate >= 0),
  constraint ck_charge_records_amount check (
       (record_type = 'CHARGE' and amount >= 0) or (record_type = 'REVERSAL' and amount <= 0)),
  constraint ck_charge_records_quantity check (
       (record_type = 'CHARGE' and quantity > 0) or (record_type = 'REVERSAL' and quantity < 0)),
  constraint ck_charge_records_period check (period_end is null or period_start is null or period_end >= period_start),
  constraint ck_charge_records_patient check (patient_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_charge_records_encounter check (encounter_reference is null or encounter_reference ~ '^[A-Za-z0-9/_-]{1,40}$'),
  constraint ck_charge_records_calc check (jsonb_typeof(calculation) = 'object'),
  constraint ck_charge_records_status check (status in ('PENDING_REVIEW','APPROVED','CANCELLED','REVERSED')),
  constraint ck_charge_records_reversal_link check ((record_type = 'REVERSAL') = (reverses_record_id is not null)),
  constraint ck_charge_records_reversal_status check (record_type <> 'REVERSAL' or status = 'APPROVED'),
  constraint ck_charge_records_reversal_reason check (
    (record_type <> 'REVERSAL' and status <> 'REVERSED')
    or (reversal_reason is not null and btrim(reversal_reason) <> '')),
  constraint ck_charge_records_corrects check (corrects_record_id is null or record_type = 'CHARGE'),
  -- approved_by may be null when the system auto-approves, so the stamp is approved_at
  constraint ck_charge_records_approved check (
    (status in ('APPROVED','REVERSED') and approved_at is not null)
    or (status not in ('APPROVED','REVERSED') and approved_at is null)),
  constraint ck_charge_records_cancelled check (
    status <> 'CANCELLED'
    or (cancel_reason is not null and btrim(cancel_reason) <> '' and cancelled_at is not null)),
  constraint ck_charge_records_export check (
    (exported_at is null) = (export_reference is null)
    and (exported_at is null or status in ('APPROVED','REVERSED'))),
  constraint ck_charge_records_text_len check (
    coalesce(char_length(cancel_reason), 0) <= 500 and coalesce(char_length(reversal_reason), 0) <= 500
    and coalesce(char_length(export_reference), 0) <= 100)
);
create index if not exists ix_charge_records_status on charge_records (facility_id, status);
create index if not exists ix_charge_records_date on charge_records (facility_id, charge_date);
create index if not exists ix_charge_records_equipment_date on charge_records (facility_id, equipment_id, charge_date);
create index if not exists ix_charge_records_patient on charge_records (facility_id, patient_reference);
create index if not exists ix_charge_records_allocation on charge_records (allocation_id) where allocation_id is not null;
create index if not exists ix_charge_records_usage_log on charge_records (usage_log_id) where usage_log_id is not null;
create unique index if not exists ux_charge_records_reversal_once
  on charge_records (facility_id, reverses_record_id) where record_type = 'REVERSAL';
-- a reversed record can be recalculated once (a cancelled recalculation frees it again)
create unique index if not exists ux_charge_records_corrects_once
  on charge_records (facility_id, corrects_record_id) where corrects_record_id is not null and status <> 'CANCELLED';

create or replace function charge_records_guard() returns trigger language plpgsql as $$
begin
  if new.status is distinct from old.status and not (
        (old.status = 'PENDING_REVIEW' and new.status in ('APPROVED', 'CANCELLED'))
     or (old.status = 'APPROVED' and new.status = 'REVERSED')) then
    raise exception 'charge record status change % -> % is not allowed', old.status, new.status
      using errcode = '23514';
  end if;
  if (new.id, new.public_id, new.facility_id, new.record_number, new.idempotency_key, new.record_type,
      new.source_type, new.allocation_id, new.usage_log_id, new.equipment_id, new.charge_mapping_id,
      new.charge_item_id, new.billing_rule, new.basis, new.unit_label, new.unit_rate, new.quantity, new.amount,
      new.period_key, new.period_start, new.period_end, new.charge_date, new.patient_reference,
      new.encounter_reference, new.department_id, new.calculation, new.reverses_record_id,
      new.corrects_record_id, new.is_active, new.created_at, new.created_by)
     is distinct from
     (old.id, old.public_id, old.facility_id, old.record_number, old.idempotency_key, old.record_type,
      old.source_type, old.allocation_id, old.usage_log_id, old.equipment_id, old.charge_mapping_id,
      old.charge_item_id, old.billing_rule, old.basis, old.unit_label, old.unit_rate, old.quantity, old.amount,
      old.period_key, old.period_start, old.period_end, old.charge_date, old.patient_reference,
      old.encounter_reference, old.department_id, old.calculation, old.reverses_record_id,
      old.corrects_record_id, old.is_active, old.created_at, old.created_by) then
    raise exception 'charge records cannot be edited' using errcode = '23514';
  end if;
  -- stamps, once set, never change
  if (old.approved_at is not null and (new.approved_at is distinct from old.approved_at
        or new.approved_by is distinct from old.approved_by))
     or (old.cancelled_at is not null and (new.cancelled_at is distinct from old.cancelled_at
        or new.cancelled_by is distinct from old.cancelled_by or new.cancel_reason is distinct from old.cancel_reason))
     or (old.exported_at is not null and (new.exported_at is distinct from old.exported_at
        or new.exported_by is distinct from old.exported_by or new.export_reference is distinct from old.export_reference))
     or (old.reversal_reason is not null and new.reversal_reason is distinct from old.reversal_reason) then
    raise exception 'approval, cancel, reversal and export stamps cannot be changed' using errcode = '23514';
  end if;
  return new;
end $$;

drop trigger if exists trg_charge_records_guard on charge_records;
create trigger trg_charge_records_guard before update on charge_records
  for each row execute function charge_records_guard();
drop trigger if exists trg_charge_records_touch on charge_records;
create trigger trg_charge_records_touch before update on charge_records
  for each row execute function touch_row();
grant select, insert, update on charge_records to bems_app;

insert into schema_version (version, description)
  values ('064', 'charge_records and immutability trigger') on conflict (version) do nothing;
