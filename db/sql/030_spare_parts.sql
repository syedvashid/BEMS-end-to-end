-- 030_spare_parts.sql  (run as bems_owner)
create table if not exists spare_parts (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  part_code text not null,
  name text not null,
  description text,
  unit text not null default 'pcs',
  reorder_level numeric(12,3) not null default 0,
  standard_unit_cost numeric(14,2),
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_spare_parts_public_id unique (public_id),
  constraint uq_spare_parts_facility_id_id unique (facility_id, id),
  constraint ck_spare_parts_rowver check (row_version >= 1),
  constraint ck_spare_parts_code check (btrim(part_code) <> ''),
  constraint ck_spare_parts_name check (btrim(name) <> ''),
  constraint ck_spare_parts_reorder check (reorder_level >= 0),
  constraint ck_spare_parts_cost check (standard_unit_cost is null or standard_unit_cost >= 0)
);
create unique index if not exists ux_spare_parts_code_active on spare_parts (facility_id, lower(part_code)) where is_active;
drop trigger if exists trg_spare_parts_touch on spare_parts;
create trigger trg_spare_parts_touch before update on spare_parts
  for each row execute function touch_row();
grant select, insert, update on spare_parts to bems_app;

create table if not exists spare_part_categories (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  spare_part_id bigint not null,
  category_id bigint not null,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  constraint uq_spare_part_categories_public_id unique (public_id),
  constraint uq_spare_part_categories_pair unique (spare_part_id, category_id),
  constraint fk_spare_part_categories_part foreign key (facility_id, spare_part_id) references spare_parts (facility_id, id),
  constraint fk_spare_part_categories_cat foreign key (facility_id, category_id) references equipment_categories (facility_id, id)
);
create index if not exists ix_spare_part_categories_cat on spare_part_categories (category_id);
grant select, insert, delete on spare_part_categories to bems_app;

create table if not exists spare_part_stock_entries (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  spare_part_id bigint not null,
  entry_type text not null,
  quantity numeric(12,3) not null,
  work_order_id bigint,
  related_entry_id bigint,
  unit_cost numeric(14,2),
  supplier_vendor_id bigint,
  reference_note text,
  reason text,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_spare_part_stock_entries_public_id unique (public_id),
  constraint uq_spare_part_stock_entries_facility_id_id unique (facility_id, id),
  constraint ck_stock_entries_type check (entry_type in ('RECEIPT','CONSUMPTION','RETURN','ADJUSTMENT')),
  constraint ck_stock_entries_qty check (
       (entry_type in ('RECEIPT','RETURN') and quantity > 0)
    or (entry_type = 'CONSUMPTION' and quantity < 0)
    or (entry_type = 'ADJUSTMENT' and quantity <> 0)),
  constraint ck_stock_entries_wo check (entry_type not in ('CONSUMPTION','RETURN') or work_order_id is not null),
  constraint ck_stock_entries_related check ((entry_type = 'RETURN') = (related_entry_id is not null)),
  constraint ck_stock_entries_reason check (entry_type <> 'ADJUSTMENT' or (reason is not null and btrim(reason) <> '')),
  constraint ck_stock_entries_cost check (unit_cost is null or unit_cost >= 0),
  constraint fk_stock_entries_part foreign key (facility_id, spare_part_id) references spare_parts (facility_id, id),
  constraint fk_stock_entries_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id),
  constraint fk_stock_entries_related foreign key (facility_id, related_entry_id) references spare_part_stock_entries (facility_id, id),
  constraint fk_stock_entries_vendor foreign key (facility_id, supplier_vendor_id) references vendors (facility_id, id)
);
create index if not exists ix_stock_entries_part on spare_part_stock_entries (spare_part_id, created_at);
create index if not exists ix_stock_entries_wo on spare_part_stock_entries (work_order_id) where work_order_id is not null;
grant select, insert on spare_part_stock_entries to bems_app;

insert into schema_version (version, description)
  values ('030', 'spare parts, compatible categories, stock ledger') on conflict (version) do nothing;
