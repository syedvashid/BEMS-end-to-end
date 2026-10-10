create table if not exists warranties (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  vendor_id bigint,
  warranty_type text not null,
  start_date date not null,
  end_date date not null,
  reference_number text,
  coverage_terms text,
  covered_parts text,
  exclusions text,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_warranties_public_id unique (public_id),
  constraint uq_warranties_facility_id unique (facility_id, id),
  constraint uq_warranties_facility_id_equipment unique (facility_id, id, equipment_id),
  constraint ck_warranties_rowver check (row_version >= 1),
  constraint ck_warranties_type check (warranty_type in ('STANDARD','EXTENDED')),
  constraint ck_warranties_dates check (end_date >= start_date),
  constraint fk_warranties_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_warranties_vendor foreign key (facility_id, vendor_id) references vendors (facility_id, id)
);
create index if not exists ix_warranties_end on warranties (facility_id, end_date);
create index if not exists ix_warranties_equipment on warranties (facility_id, equipment_id);
drop trigger if exists trg_warranties_touch on warranties;
create trigger trg_warranties_touch before update on warranties
  for each row execute function touch_row();
grant select, insert, update on warranties to bems_app;

create table if not exists warranty_claims (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  warranty_id bigint not null,
  equipment_id bigint not null,
  work_order_id bigint,
  claim_number text,
  claim_date date not null,
  description text not null,
  status text not null default 'RAISED',
  claim_amount numeric(14,2),
  resolved_date date,
  resolution_notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_warranty_claims_public_id unique (public_id),
  constraint ck_warranty_claims_rowver check (row_version >= 1),
  constraint ck_warranty_claims_status check (status in ('RAISED','ACCEPTED','REJECTED','RESOLVED')),
  constraint ck_warranty_claims_amount check (claim_amount is null or claim_amount >= 0),
  constraint ck_warranty_claims_resolved check (resolved_date is null or resolved_date >= claim_date),
  constraint ck_warranty_claims_desc check (btrim(description) <> ''),
  -- stronger than two separate FKs: the claim's equipment must be the warranty's equipment
  constraint fk_warranty_claims_warranty foreign key (facility_id, warranty_id, equipment_id)
    references warranties (facility_id, id, equipment_id),
  constraint fk_warranty_claims_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_warranty_claims_wo foreign key (facility_id, work_order_id)
    references work_orders (facility_id, id)
);
create index if not exists ix_warranty_claims_warranty on warranty_claims (facility_id, warranty_id);
create index if not exists ix_warranty_claims_equipment on warranty_claims (facility_id, equipment_id);
drop trigger if exists trg_warranty_claims_touch on warranty_claims;
create trigger trg_warranty_claims_touch before update on warranty_claims
  for each row execute function touch_row();
grant select, insert, update on warranty_claims to bems_app;

insert into schema_version (version, description) values ('033', 'warranties and warranty claims')
  on conflict (version) do nothing;