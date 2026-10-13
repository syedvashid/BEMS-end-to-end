-- 054 disposals (run as bems_owner)
begin;

create table if not exists disposals (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  disposal_number text not null,
  equipment_id bigint not null,
  condemnation_request_id bigint not null,
  disposal_method text not null,
  disposal_date date,
  recipient_name text,
  recipient_vendor_id bigint,
  proceeds_amount numeric(14,2) not null default 0,
  decontamination_done boolean not null default false,
  decontamination_notes text,
  data_wipe_required boolean not null default false,
  data_wipe_done boolean not null default false,
  recycler_name text,
  ewaste_certificate_number text,
  book_value_at_disposal numeric(14,2),
  gain_loss numeric(14,2),
  status text not null default 'IN_PROGRESS',
  completed_at timestamptz,
  completed_by bigint references users (id),
  cancel_reason text,
  notes text,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_disposals_public_id unique (public_id),
  constraint uq_disposals_facility_id_id unique (facility_id, id),
  constraint ck_disposals_rowver check (row_version >= 1),
  constraint fk_disposals_equipment foreign key (facility_id, equipment_id)
    references equipment (facility_id, id),
  constraint fk_disposals_request foreign key (facility_id, condemnation_request_id)
    references condemnation_requests (facility_id, id),
  constraint fk_disposals_recipient_vendor foreign key (facility_id, recipient_vendor_id)
    references vendors (facility_id, id),
  constraint ck_disposals_method check (disposal_method in (
    'SOLD','SCRAPPED_E_WASTE','DONATED','RETURNED_TO_VENDOR','TRADE_IN','AUCTIONED','LOST_MISSING')),
  constraint ck_disposals_status check (status in ('IN_PROGRESS','COMPLETED','CANCELLED')),
  constraint ck_disposals_proceeds check (proceeds_amount >= 0),
  constraint ck_disposals_completed check (
    status <> 'COMPLETED' or (completed_at is not null and completed_by is not null and disposal_date is not null))
);
create unique index if not exists ux_disposals_number_active
  on disposals (facility_id, disposal_number) where is_active;
create unique index if not exists ux_disposals_live_equipment_active
  on disposals (facility_id, equipment_id) where status in ('IN_PROGRESS','COMPLETED') and is_active;
create index if not exists ix_disposals_request on disposals (facility_id, condemnation_request_id);
create index if not exists ix_disposals_vendor on disposals (facility_id, recipient_vendor_id);
create index if not exists ix_disposals_status_date on disposals (facility_id, status, disposal_date desc);

create or replace function fn_disposals_final_guard() returns trigger
language plpgsql as $$
begin
  if old.status in ('COMPLETED','CANCELLED') then
    raise exception 'A % disposal cannot be changed', lower(old.status) using errcode = '23514';
  end if;
  return new;
end $$;

drop trigger if exists trg_disposals_final on disposals;
create trigger trg_disposals_final before update on disposals
  for each row execute function fn_disposals_final_guard();
drop trigger if exists trg_disposals_touch on disposals;
create trigger trg_disposals_touch before update on disposals
  for each row execute function touch_row();
grant select, insert, update on disposals to bems_app;

insert into schema_version (version, description)
  values ('054', 'disposals') on conflict (version) do nothing;
commit;
