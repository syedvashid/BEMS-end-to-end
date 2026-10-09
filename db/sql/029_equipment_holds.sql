-- 029_equipment_holds.sql  (run as bems_owner)
create table if not exists equipment_holds (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  hold_type text not null,
  source_type text not null,
  work_order_id bigint,
  reason text not null,
  started_at timestamptz not null default now(),
  released_at timestamptz,
  released_by bigint references users (id),
  release_reason text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_holds_public_id unique (public_id),
  constraint ck_equipment_holds_rowver check (row_version >= 1),
  constraint ck_equipment_holds_type check (hold_type in ('MAINTENANCE','OUT_OF_SERVICE')),
  constraint ck_equipment_holds_source check (source_type in ('WORK_ORDER','MANUAL')),
  constraint ck_equipment_holds_source_wo check ((source_type = 'WORK_ORDER') = (work_order_id is not null)),
  constraint ck_equipment_holds_reason check (btrim(reason) <> ''),
  constraint ck_equipment_holds_released check (released_at is null or released_at >= started_at),
  constraint fk_equipment_holds_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_equipment_holds_wo foreign key (facility_id, work_order_id) references work_orders (facility_id, id)
);
create index if not exists ix_equipment_holds_open on equipment_holds (equipment_id) where released_at is null;
create index if not exists ix_equipment_holds_equipment on equipment_holds (facility_id, equipment_id, started_at desc);
create unique index if not exists ux_equipment_holds_wo_type_open
  on equipment_holds (work_order_id, hold_type) where released_at is null and work_order_id is not null;
drop trigger if exists trg_equipment_holds_touch on equipment_holds;
create trigger trg_equipment_holds_touch before update on equipment_holds
  for each row execute function touch_row();
grant select, insert, update on equipment_holds to bems_app;

insert into schema_version (version, description)
  values ('029', 'equipment_holds') on conflict (version) do nothing;
