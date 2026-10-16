-- 062: charge_items and charge_settings (run as bems_owner)

-- unique (facility_id, id) guard needed by the composite FK of charge_records (usage logs did not have one yet)
do $$
begin
  if not exists (select 1 from pg_constraint
                  where conrelid = 'equipment_usage_logs'::regclass and contype = 'u'
                    and pg_get_constraintdef(oid) = 'UNIQUE (facility_id, id)') then
    alter table equipment_usage_logs add constraint uq_equipment_usage_logs_facility_id unique (facility_id, id);
  end if;
end $$;

create table if not exists charge_items (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  item_code varchar(50) not null,
  name varchar(200) not null,
  unit_label varchar(30) not null,
  default_rate numeric(14,2) not null,
  description varchar(500),
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_charge_items_public_id unique (public_id),
  constraint uq_charge_items_facility_id unique (facility_id, id),
  constraint ck_charge_items_rowver check (row_version >= 1),
  constraint ck_charge_items_code check (item_code ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,49}$'),
  constraint ck_charge_items_name check (btrim(name) <> ''),
  constraint ck_charge_items_unit check (btrim(unit_label) <> ''),
  constraint ck_charge_items_rate check (default_rate >= 0)
);
create unique index if not exists ux_charge_items_code_active
  on charge_items (facility_id, lower(item_code)) where is_active;
drop trigger if exists trg_charge_items_touch on charge_items;
create trigger trg_charge_items_touch before update on charge_items
  for each row execute function touch_row();
grant select, insert, update on charge_items to bems_app;

create table if not exists charge_settings (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  auto_approve boolean not null default false,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_charge_settings_public_id unique (public_id),
  constraint ck_charge_settings_rowver check (row_version >= 1)
);
create unique index if not exists ux_charge_settings_facility_active
  on charge_settings (facility_id) where is_active;
drop trigger if exists trg_charge_settings_touch on charge_settings;
create trigger trg_charge_settings_touch before update on charge_settings
  for each row execute function touch_row();
grant select, insert, update on charge_settings to bems_app;

insert into schema_version (version, description)
  values ('062', 'charge_items, charge_settings') on conflict (version) do nothing;
