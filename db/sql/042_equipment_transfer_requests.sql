begin;

create table if not exists equipment_transfer_requests (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  equipment_id bigint not null,
  from_department_id bigint,
  from_location_id bigint,
  to_location_id bigint not null,
  to_department_id bigint,
  reason text not null,
  status text not null default 'PENDING',
  decided_by bigint references users (id),
  decided_at timestamptz,
  decision_note text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_equipment_transfer_requests_public_id unique (public_id),
  constraint ck_equipment_transfer_requests_rowver check (row_version >= 1),
  constraint fk_xfer_equipment foreign key (facility_id, equipment_id) references equipment (facility_id, id),
  constraint fk_xfer_from_dept foreign key (facility_id, from_department_id) references departments (facility_id, id),
  constraint fk_xfer_from_loc foreign key (facility_id, from_location_id) references locations (facility_id, id),
  constraint fk_xfer_to_loc foreign key (facility_id, to_location_id) references locations (facility_id, id),
  constraint fk_xfer_to_dept foreign key (facility_id, to_department_id) references departments (facility_id, id),
  constraint ck_xfer_reason check (length(btrim(reason)) > 0 and length(reason) <= 1000),
  constraint ck_xfer_status check (status in ('PENDING','APPROVED','REJECTED','CANCELLED')),
  constraint ck_xfer_note check (coalesce(length(decision_note), 0) <= 1000
    and (status <> 'REJECTED' or length(btrim(coalesce(decision_note, ''))) > 0)),
  constraint ck_xfer_decided check ((status = 'PENDING') = (decided_at is null))
);

create unique index if not exists ux_equipment_transfer_requests_pending_active
  on equipment_transfer_requests (facility_id, equipment_id) where status = 'PENDING' and is_active;
create index if not exists ix_xfer_status on equipment_transfer_requests (facility_id, status, created_at desc);
create index if not exists ix_xfer_to_location on equipment_transfer_requests (facility_id, to_location_id)
  where status = 'PENDING' and is_active;
create index if not exists ix_xfer_to_department on equipment_transfer_requests (facility_id, to_department_id)
  where status = 'PENDING' and is_active;

create or replace function trg_xfer_status_guard() returns trigger language plpgsql as $$
begin
  if old.status <> 'PENDING' and new.status is distinct from old.status then
    raise exception 'transfer request status is final' using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger if exists trg_equipment_transfer_requests_status on equipment_transfer_requests;
create trigger trg_equipment_transfer_requests_status before update on equipment_transfer_requests
  for each row execute function trg_xfer_status_guard();

drop trigger if exists trg_equipment_transfer_requests_touch on equipment_transfer_requests;
create trigger trg_equipment_transfer_requests_touch before update on equipment_transfer_requests
  for each row execute function touch_row();

grant select, insert, update on equipment_transfer_requests to bems_app;

insert into schema_version (version, description)
  values ('042', 'equipment_transfer_requests') on conflict (version) do nothing;
commit;