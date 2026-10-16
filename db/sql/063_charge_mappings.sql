-- 063: charge_mappings (run as bems_owner)
create table if not exists charge_mappings (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint,
  category_id bigint,
  charge_item_id bigint not null,
  billing_rule varchar(20) not null,
  basis varchar(15) not null default 'ALLOCATION',
  rate_override numeric(14,2),
  minimum_billable_minutes integer not null default 0,
  grace_minutes integer not null default 0,
  rounding varchar(10) not null default 'UP',
  daily_cap_amount numeric(14,2),
  day_block_mode varchar(15) not null default 'CALENDAR_DAY',
  bundle_reference varchar(100),
  effective_from date not null,
  effective_to date,
  notes varchar(500),
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_charge_mappings_public_id unique (public_id),
  constraint uq_charge_mappings_facility_id unique (facility_id, id),
  constraint ck_charge_mappings_rowver check (row_version >= 1),
  constraint fk_charge_mappings_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_charge_mappings_category foreign key (facility_id, category_id) references equipment_categories (facility_id, id),
  constraint fk_charge_mappings_item foreign key (facility_id, charge_item_id) references charge_items (facility_id, id),
  constraint ck_charge_mappings_scope check ((equipment_id is null) <> (category_id is null)),
  constraint ck_charge_mappings_rule check (billing_rule in
    ('HOURLY','DAILY','PER_USE','PER_SESSION','PER_ADMISSION','BUNDLED','DISABLED')),
  constraint ck_charge_mappings_basis check (basis in ('ALLOCATION','USAGE_LOG')),
  constraint ck_charge_mappings_rule_basis check (
       (billing_rule = 'HOURLY' and basis in ('ALLOCATION','USAGE_LOG'))
    or (billing_rule = 'DAILY' and basis = 'ALLOCATION')
    or (billing_rule = 'PER_USE' and basis = 'ALLOCATION')
    or (billing_rule = 'PER_SESSION' and basis = 'USAGE_LOG')
    or (billing_rule = 'PER_ADMISSION' and basis in ('ALLOCATION','USAGE_LOG'))
    or billing_rule in ('BUNDLED','DISABLED')),
  constraint ck_charge_mappings_rate check (rate_override is null or rate_override >= 0),
  constraint ck_charge_mappings_min check (minimum_billable_minutes >= 0),
  constraint ck_charge_mappings_grace check (grace_minutes >= 0),
  constraint ck_charge_mappings_rounding check (rounding in ('UP','NEAREST')),
  constraint ck_charge_mappings_cap check (daily_cap_amount is null or daily_cap_amount > 0),
  constraint ck_charge_mappings_daymode check (day_block_mode in ('CALENDAR_DAY','BLOCK_24H')),
  constraint ck_charge_mappings_bundle check (
    billing_rule <> 'BUNDLED' or (bundle_reference is not null and btrim(bundle_reference) <> '')),
  constraint ck_charge_mappings_dates check (effective_to is null or effective_to >= effective_from),
  constraint ex_charge_mappings_equipment_period exclude using gist (
    facility_id with =, equipment_id with =, daterange(effective_from, effective_to, '[]') with &&)
    where (equipment_id is not null and is_active),
  constraint ex_charge_mappings_category_period exclude using gist (
    facility_id with =, category_id with =, daterange(effective_from, effective_to, '[]') with &&)
    where (category_id is not null and is_active)
);
create index if not exists ix_charge_mappings_item on charge_mappings (facility_id, charge_item_id);
create index if not exists ix_charge_mappings_equipment on charge_mappings (facility_id, equipment_id)
  where equipment_id is not null;
create index if not exists ix_charge_mappings_category on charge_mappings (facility_id, category_id)
  where category_id is not null;
drop trigger if exists trg_charge_mappings_touch on charge_mappings;
create trigger trg_charge_mappings_touch before update on charge_mappings
  for each row execute function touch_row();
grant select, insert, update on charge_mappings to bems_app;

insert into schema_version (version, description)
  values ('063', 'charge_mappings') on conflict (version) do nothing;
