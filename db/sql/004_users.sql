create table if not exists users (
    id                   bigint generated always as identity primary key,
    public_id            uuid        not null default gen_random_uuid(),
    username             citext      not null,
    full_name            text        not null,
    email                citext,
    phone                text,
    employee_code        text,
    designation          text,
    -- reserved for the future auth phase, unused now
    password_hash        text,
    failed_login_count   integer     not null default 0,
    locked_until         timestamptz,
    last_login_at        timestamptz,
    must_change_password boolean     not null default false,
    created_at           timestamptz not null default now(),
    created_by           bigint      references users (id),
    updated_at           timestamptz not null default now(),
    updated_by           bigint      references users (id),
    is_active            boolean     not null default true,
    row_version          integer     not null default 1,
    constraint uq_users_public_id unique (public_id),
    constraint ck_users_username  check (username ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$'),
    constraint ck_users_fullname  check (length(btrim(full_name)) > 0),
    constraint ck_users_email     check (email is null or position('@' in email::text) > 1),
    constraint ck_users_failed    check (failed_login_count >= 0),
    constraint ck_users_rowver    check (row_version >= 1)
);

create unique index if not exists ux_users_username_active
    on users (username) where is_active;

drop trigger if exists trg_users_touch on users;
create trigger trg_users_touch before update on users
    for each row execute function touch_row();

-- facilities.created_by / updated_by now that users exists
do $$ begin
    alter table facilities add constraint fk_facilities_created_by
        foreign key (created_by) references users (id);
exception when duplicate_object then null; end $$;

do $$ begin
    alter table facilities add constraint fk_facilities_updated_by
        foreign key (updated_by) references users (id);
exception when duplicate_object then null; end $$;

insert into schema_version (version, description)
values ('004', 'users') on conflict (version) do nothing;