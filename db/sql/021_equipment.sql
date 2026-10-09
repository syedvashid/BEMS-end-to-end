-- 021: equipment registry table, lifecycle transitions table and enforcement trigger. Run as bems_owner.
create table if not exists equipment (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),

  asset_tag text not null,
  qr_code_value text not null,
  legacy_asset_id text,
  equipment_model_id bigint not null,
  name text not null,
  serial_number text,

  lifecycle_stage text not null default 'RECEIVED',
  operational_state text,
  owning_department_id bigint,
  current_location_id bigint,
  criticality text not null default 'MEDIUM',

  ownership_type text not null default 'OWNED',
  owner_vendor_id bigint,
  ownership_end_date date,
  funding_source_id bigint,

  supplier_vendor_id bigint,
  purchase_order_number text,
  purchase_order_date date,
  grn_number text,
  grn_date date,
  invoice_number text,
  invoice_date date,
  purchase_cost numeric(14,2),
  installation_cost numeric(14,2),

  expected_life_years integer,
  custom_attributes jsonb not null default '{}'::jsonb,
  notes text,
  is_legacy_entry boolean not null default false,

  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,

  constraint uq_equipment_public_id unique (public_id),
  constraint uq_equipment_facility_id_id unique (facility_id, id),
  constraint uq_equipment_asset_tag unique (facility_id, asset_tag),
  constraint uq_equipment_qr_code unique (qr_code_value),
  constraint ck_equipment_rowver check (row_version >= 1),
  constraint ck_equipment_asset_tag_fmt check (asset_tag ~ '^EQ-[0-9]{4}-[0-9]{6}$'),
  constraint ck_equipment_qr_fmt check (qr_code_value ~ '^BEMS-[A-Z0-9]{12}$'),
  constraint ck_equipment_name check (btrim(name) <> '' and char_length(name) <= 200),
  constraint ck_equipment_serial check (serial_number is null or (btrim(serial_number) <> '' and char_length(serial_number) <= 100)),
  constraint ck_equipment_legacy_id check (legacy_asset_id is null or (btrim(legacy_asset_id) <> '' and char_length(legacy_asset_id) <= 100)),
  constraint ck_equipment_stage check (lifecycle_stage in ('RECEIVED','INSTALLED','COMMISSIONED','REJECTED','CONDEMNED','DISPOSED')),
  constraint ck_equipment_opstate check (operational_state is null or operational_state in ('IN_SERVICE','UNDER_MAINTENANCE','OUT_OF_SERVICE')),
  constraint ck_equipment_state_pair check ((lifecycle_stage = 'COMMISSIONED') = (operational_state is not null)),
  constraint ck_equipment_criticality check (criticality in ('LOW','MEDIUM','HIGH','CRITICAL')),
  constraint ck_equipment_ownership_type check (ownership_type in ('OWNED','LEASED','RENTAL','LOAN_DEMO','VENDOR_PLACED')),
  constraint ck_equipment_owner_vendor check (ownership_type = 'OWNED' or owner_vendor_id is not null),
  constraint ck_equipment_purchase_cost check (purchase_cost is null or purchase_cost >= 0),
  constraint ck_equipment_install_cost check (installation_cost is null or installation_cost >= 0),
  constraint ck_equipment_life check (expected_life_years is null or expected_life_years > 0),
  constraint ck_equipment_custom_attrs check (jsonb_typeof(custom_attributes) = 'object'),
  constraint ck_equipment_text_len check (
    coalesce(char_length(purchase_order_number),0) <= 100 and coalesce(char_length(grn_number),0) <= 100
    and coalesce(char_length(invoice_number),0) <= 100 and coalesce(char_length(notes),0) <= 2000),

  constraint fk_equipment_model foreign key (facility_id, equipment_model_id) references equipment_models (facility_id, id),
  constraint fk_equipment_department foreign key (facility_id, owning_department_id) references departments (facility_id, id),
  constraint fk_equipment_location foreign key (facility_id, current_location_id) references locations (facility_id, id),
  constraint fk_equipment_owner_vendor foreign key (facility_id, owner_vendor_id) references vendors (facility_id, id),
  constraint fk_equipment_supplier foreign key (facility_id, supplier_vendor_id) references vendors (facility_id, id),
  constraint fk_equipment_funding foreign key (facility_id, funding_source_id) references funding_sources (facility_id, id)
);

create unique index if not exists ux_equipment_legacy_asset_id_active
  on equipment (facility_id, lower(legacy_asset_id)) where is_active and legacy_asset_id is not null;
create unique index if not exists ux_equipment_serial_active
  on equipment (facility_id, equipment_model_id, lower(serial_number)) where is_active and serial_number is not null;

create index if not exists ix_equipment_stage on equipment (facility_id, lifecycle_stage);
create index if not exists ix_equipment_location on equipment (facility_id, current_location_id);
create index if not exists ix_equipment_model on equipment (facility_id, equipment_model_id);
create index if not exists ix_equipment_department on equipment (facility_id, owning_department_id);
create index if not exists ix_equipment_opstate on equipment (facility_id, operational_state);
create index if not exists ix_equipment_supplier on equipment (facility_id, supplier_vendor_id) where supplier_vendor_id is not null;
create index if not exists ix_equipment_owner_vendor on equipment (facility_id, owner_vendor_id) where owner_vendor_id is not null;
create index if not exists ix_equipment_funding on equipment (facility_id, funding_source_id) where funding_source_id is not null;
create index if not exists ix_equipment_invoice_date on equipment (facility_id, invoice_date);

-- Global reference table of allowed lifecycle transitions
create table if not exists equipment_lifecycle_transitions (
  from_stage text not null,
  to_stage text not null,
  primary key (from_stage, to_stage),
  constraint ck_elt_from check (from_stage in ('RECEIVED','INSTALLED','COMMISSIONED','REJECTED','CONDEMNED','DISPOSED')),
  constraint ck_elt_to check (to_stage in ('RECEIVED','INSTALLED','COMMISSIONED','REJECTED','CONDEMNED','DISPOSED'))
);
insert into equipment_lifecycle_transitions (from_stage, to_stage) values
  ('RECEIVED','INSTALLED'), ('RECEIVED','REJECTED'), ('INSTALLED','COMMISSIONED'),
  ('INSTALLED','REJECTED'), ('COMMISSIONED','CONDEMNED'), ('CONDEMNED','DISPOSED')
on conflict do nothing;
grant select on equipment_lifecycle_transitions to bems_app;

create or replace function equipment_enforce_lifecycle() returns trigger
language plpgsql set search_path = public as $$
begin
  if tg_op = 'INSERT' then
    if new.lifecycle_stage = 'RECEIVED' or (new.lifecycle_stage = 'COMMISSIONED' and new.is_legacy_entry) then
      return new;
    end if;
    raise exception 'Invalid initial lifecycle stage' using errcode = '23514';
  end if;
  -- UPDATE
  if new.asset_tag is distinct from old.asset_tag
     or new.qr_code_value is distinct from old.qr_code_value
     or new.facility_id is distinct from old.facility_id then
    raise exception 'asset_tag, qr_code_value and facility_id are immutable' using errcode = '23514';
  end if;
  if new.lifecycle_stage is distinct from old.lifecycle_stage then
    if not exists (select 1 from equipment_lifecycle_transitions
                    where from_stage = old.lifecycle_stage and to_stage = new.lifecycle_stage) then
      raise exception 'Lifecycle transition % -> % is not allowed', old.lifecycle_stage, new.lifecycle_stage
        using errcode = '23514';
    end if;
  end if;
  return new;
end $$;

drop trigger if exists trg_equipment_lifecycle on equipment;
create trigger trg_equipment_lifecycle before insert or update on equipment
  for each row execute function equipment_enforce_lifecycle();
drop trigger if exists trg_equipment_touch on equipment;
create trigger trg_equipment_touch before update on equipment
  for each row execute function touch_row();

grant select, insert, update on equipment to bems_app;

insert into schema_version (version, description)
  values ('021', 'equipment, lifecycle transitions, lifecycle trigger') on conflict (version) do nothing;
