create table if not exists permissions (
    id          bigint generated always as identity primary key,
    public_id   uuid        not null default gen_random_uuid(),
    code        text        not null,
    module      text        not null,
    description text,
    created_at  timestamptz not null default now(),
    created_by  bigint      references users (id),
    updated_at  timestamptz not null default now(),
    updated_by  bigint      references users (id),
    is_active   boolean     not null default true,
    row_version integer     not null default 1,
    constraint uq_permissions_public_id unique (public_id),
    constraint uq_permissions_code      unique (code),
    constraint ck_permissions_code   check (code ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),
    constraint ck_permissions_module check (module ~ '^[a-z][a-z0-9_]*$'),
    constraint ck_permissions_rowver check (row_version >= 1)
);

create table if not exists roles (
    id          bigint generated always as identity primary key,
    public_id   uuid        not null default gen_random_uuid(),
    code        text        not null,
    name        text        not null,
    description text,
    is_system   boolean     not null default false,
    created_at  timestamptz not null default now(),
    created_by  bigint      references users (id),
    updated_at  timestamptz not null default now(),
    updated_by  bigint      references users (id),
    is_active   boolean     not null default true,
    row_version integer     not null default 1,
    constraint uq_roles_public_id unique (public_id),
    constraint ck_roles_code   check (code ~ '^[A-Z][A-Z0-9_]*$'),
    constraint ck_roles_name   check (length(btrim(name)) > 0),
    constraint ck_roles_system_active check (not is_system or is_active),  -- system roles can't be soft-deleted
    constraint ck_roles_rowver check (row_version >= 1)
);
create unique index if not exists ux_roles_code_active on roles (code) where is_active;

-- Join table: replaced as a set by PUT, audited as ROLE_PERMISSIONS_CHANGE.
-- Documented exception: no is_active / row_version / updated_*.
create table if not exists role_permissions (
    id            bigint generated always as identity primary key,
    role_id       bigint      not null references roles (id),
    permission_id bigint      not null references permissions (id),
    created_at    timestamptz not null default now(),
    created_by    bigint      references users (id),
    constraint uq_role_permissions unique (role_id, permission_id)
);
create index if not exists ix_role_permissions_perm on role_permissions (permission_id);

create table if not exists user_facility_roles (
    id          bigint generated always as identity primary key,
    public_id   uuid        not null default gen_random_uuid(),
    user_id     bigint      not null references users (id),
    facility_id bigint      not null references facilities (id),
    role_id     bigint      not null references roles (id),
    created_at  timestamptz not null default now(),
    created_by  bigint      references users (id),
    updated_at  timestamptz not null default now(),
    updated_by  bigint      references users (id),
    is_active   boolean     not null default true,
    row_version integer     not null default 1,
    constraint uq_ufr_public_id unique (public_id),
    constraint ck_ufr_rowver check (row_version >= 1)
);
create unique index if not exists ux_ufr_active
    on user_facility_roles (user_id, facility_id, role_id) where is_active;
create index if not exists ix_ufr_facility_user
    on user_facility_roles (facility_id, user_id) where is_active;
create index if not exists ix_ufr_user
    on user_facility_roles (user_id) where is_active;

drop trigger if exists trg_permissions_touch on permissions;
create trigger trg_permissions_touch before update on permissions
    for each row execute function touch_row();
drop trigger if exists trg_roles_touch on roles;
create trigger trg_roles_touch before update on roles
    for each row execute function touch_row();
drop trigger if exists trg_ufr_touch on user_facility_roles;
create trigger trg_ufr_touch before update on user_facility_roles
    for each row execute function touch_row();

insert into schema_version (version, description)
values ('005', 'permissions, roles, role_permissions, user_facility_roles')
on conflict (version) do nothing;