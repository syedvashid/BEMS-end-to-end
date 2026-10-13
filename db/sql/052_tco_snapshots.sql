-- 052 TCO snapshots (run as bems_owner)
begin;

create table if not exists tco_snapshots (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  as_of_date date not null,
  acquisition_cost numeric(14,2) not null default 0,
  installation_cost numeric(14,2) not null default 0,
  labour_cost numeric(14,2) not null default 0,
  vendor_cost numeric(14,2) not null default 0,
  parts_cost numeric(14,2) not null default 0,
  amc_cost numeric(14,2) not null default 0,
  salvage_value numeric(14,2) not null default 0,
  total_cost_of_ownership numeric(14,2) not null default 0,
  maintenance_cost numeric(14,2) not null default 0,
  maintenance_cost_ratio_percent numeric(10,2),
  age_years numeric(6,2),
  expected_life_years numeric(5,2),
  usage_hours numeric(12,2) not null default 0,
  session_count integer not null default 0,
  cost_per_hour numeric(14,2),
  cost_per_use numeric(14,2),
  threshold_percent numeric(6,2) not null,
  replacement_indicator text not null default 'NONE',
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_tco_snapshots_public_id unique (public_id),
  constraint uq_tco_snapshots_equipment_date unique (equipment_id, as_of_date),
  constraint fk_tco_snapshots_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint ck_tco_snapshots_indicator check (replacement_indicator in ('NONE','REVIEW','REPLACE_RECOMMENDED')),
  constraint ck_tco_snapshots_counts check (usage_hours >= 0 and session_count >= 0)
);
create index if not exists ix_tco_snapshots_facility_date on tco_snapshots (facility_id, as_of_date desc);
create index if not exists ix_tco_snapshots_facility_indicator on tco_snapshots (facility_id, replacement_indicator);
grant select, insert on tco_snapshots to bems_app;

insert into schema_version (version, description)
  values ('052', 'tco snapshots') on conflict (version) do nothing;
commit;
