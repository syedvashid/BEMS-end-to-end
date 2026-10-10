create table if not exists amc_contracts (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  contract_number text not null,
  vendor_id bigint not null,
  contract_type text not null,
  start_date date not null,
  end_date date not null,
  contract_cost numeric(14,2) not null default 0,
  covered_scope text,
  exclusions text,
  visit_frequency_per_year smallint not null default 0,
  response_sla_hours integer,
  uptime_guarantee_percent numeric(5,2),
  penalty_terms text,
  renewed_from_contract_id bigint,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_amc_contracts_public_id unique (public_id),
  constraint uq_amc_contracts_facility_id unique (facility_id, id),
  constraint ck_amc_contracts_rowver check (row_version >= 1),
  constraint ck_amc_contracts_number check (btrim(contract_number) <> ''),
  constraint ck_amc_contracts_type check (contract_type in ('COMPREHENSIVE','NON_COMPREHENSIVE')),
  constraint ck_amc_contracts_dates check (end_date >= start_date),
  constraint ck_amc_contracts_cost check (contract_cost >= 0),
  constraint ck_amc_contracts_visits check (visit_frequency_per_year >= 0),
  constraint ck_amc_contracts_sla check (response_sla_hours is null or response_sla_hours > 0),
  constraint ck_amc_contracts_uptime check (uptime_guarantee_percent is null
    or (uptime_guarantee_percent >= 0 and uptime_guarantee_percent <= 100)),
  constraint ck_amc_contracts_not_self_renewal check (renewed_from_contract_id is null or renewed_from_contract_id <> id),
  constraint fk_amc_contracts_vendor foreign key (facility_id, vendor_id) references vendors (facility_id, id),
  constraint fk_amc_contracts_renewed foreign key (facility_id, renewed_from_contract_id)
    references amc_contracts (facility_id, id)
);
create unique index if not exists ux_amc_contracts_number_active
  on amc_contracts (facility_id, lower(contract_number)) where is_active;
create index if not exists ix_amc_contracts_end on amc_contracts (facility_id, end_date);
create index if not exists ix_amc_contracts_vendor on amc_contracts (facility_id, vendor_id);
drop trigger if exists trg_amc_contracts_touch on amc_contracts;
create trigger trg_amc_contracts_touch before update on amc_contracts
  for each row execute function touch_row();
grant select, insert, update on amc_contracts to bems_app;

create table if not exists amc_coverages (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  amc_contract_id bigint not null,
  equipment_id bigint not null,
  allocated_cost numeric(14,2),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_amc_coverages_public_id unique (public_id),
  constraint uq_amc_coverages_contract_equipment unique (amc_contract_id, equipment_id),
  constraint ck_amc_coverages_cost check (allocated_cost is null or allocated_cost >= 0),
  constraint fk_amc_coverages_contract foreign key (facility_id, amc_contract_id)
    references amc_contracts (facility_id, id),
  constraint fk_amc_coverages_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id)
);
create index if not exists ix_amc_coverages_equipment on amc_coverages (facility_id, equipment_id);
grant select, insert, delete on amc_coverages to bems_app;

insert into schema_version (version, description) values ('034', 'AMC contracts and coverages')
  on conflict (version) do nothing;