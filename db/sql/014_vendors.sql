create table if not exists vendors (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  name varchar(200) not null,
  is_manufacturer boolean not null default false,
  is_supplier boolean not null default false,
  is_service_provider boolean not null default false,
  gstin varchar(15),
  pan varchar(10),
  address_line1 varchar(200),
  address_line2 varchar(200),
  city varchar(100),
  state varchar(100),
  pin_code varchar(6),
  phone varchar(20),
  email varchar(254),
  rating smallint,
  notes varchar(1000),
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_vendors_public_id unique (public_id),
  constraint uq_vendors_facility_id_id unique (facility_id, id),
  constraint ck_vendors_type check (is_manufacturer or is_supplier or is_service_provider),
  constraint ck_vendors_gstin check (gstin is null or gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),
  constraint ck_vendors_pan check (pan is null or pan ~ '^[A-Z]{5}[0-9]{4}[A-Z]$'),
  constraint ck_vendors_pin check (pin_code is null or pin_code ~ '^[1-9][0-9]{5}$'),
  constraint ck_vendors_rating check (rating is null or rating between 1 and 5),
  constraint ck_vendors_rowver check (row_version >= 1)
);
create unique index if not exists ux_vendors_name_active
  on vendors (facility_id, lower(name)) where is_active;
drop trigger if exists trg_vendors_touch on vendors;
create trigger trg_vendors_touch before update on vendors
  for each row execute function touch_row();
grant select, insert, update on vendors to bems_app;

create table if not exists vendor_contacts (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  vendor_id bigint not null,
  name varchar(200) not null,
  designation varchar(100),
  phone varchar(20),
  email varchar(254),
  contact_type varchar(20) not null default 'OTHER',
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  updated_at timestamptz not null default now(),
  updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_vendor_contacts_public_id unique (public_id),
  constraint fk_vendor_contacts_vendor foreign key (facility_id, vendor_id)
    references vendors (facility_id, id),
  constraint ck_vendor_contacts_type check (contact_type in ('SALES','SERVICE','ESCALATION','OTHER')),
  constraint ck_vendor_contacts_rowver check (row_version >= 1)
);
create unique index if not exists ux_vendor_contacts_primary_active
  on vendor_contacts (vendor_id) where is_active and is_primary;
create index if not exists ix_vendor_contacts_vendor on vendor_contacts (facility_id, vendor_id);
drop trigger if exists trg_vendor_contacts_touch on vendor_contacts;
create trigger trg_vendor_contacts_touch before update on vendor_contacts
  for each row execute function touch_row();
grant select, insert, update on vendor_contacts to bems_app;

insert into schema_version (version, description)
  values ('014', 'vendors and vendor_contacts') on conflict (version) do nothing;