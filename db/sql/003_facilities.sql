create table if not exists facilities (
    id                  bigint generated always as identity primary key,
    public_id           uuid        not null default gen_random_uuid(),
    code                text        not null,
    name                text        not null,
    facility_type       text        not null default 'HOSPITAL',
    parent_facility_id  bigint      references facilities (id),
    address_line1       text,
    address_line2       text,
    city                text,
    state               text,
    pin_code            text,
    phone               text,
    email               text,
    registration_number text,
    timezone            text        not null default 'Asia/Kolkata',
    created_at          timestamptz not null default now(),
    created_by          bigint,     -- FK to users added in 004
    updated_at          timestamptz not null default now(),
    updated_by          bigint,     -- FK to users added in 004
    is_active           boolean     not null default true,
    row_version         integer     not null default 1,
    constraint uq_facilities_public_id unique (public_id),
    constraint ck_facilities_code  check (code ~ '^[A-Z0-9][A-Z0-9_-]{1,29}$'),
    constraint ck_facilities_name  check (length(btrim(name)) > 0),
    constraint ck_facilities_type  check (facility_type in ('HOSPITAL','CLINIC','CAMPUS','OTHER')),
    constraint ck_facilities_pin   check (pin_code is null or pin_code ~ '^[1-9][0-9]{5}$'),
    constraint ck_facilities_parent check (parent_facility_id is null or parent_facility_id <> id),
    constraint ck_facilities_rowver check (row_version >= 1)
);

create unique index if not exists ux_facilities_code_active
    on facilities (lower(code)) where is_active;
create index if not exists ix_facilities_parent
    on facilities (parent_facility_id) where parent_facility_id is not null;

drop trigger if exists trg_facilities_touch on facilities;
create trigger trg_facilities_touch before update on facilities
    for each row execute function touch_row();

insert into schema_version (version, description)
values ('003', 'facilities') on conflict (version) do nothing;