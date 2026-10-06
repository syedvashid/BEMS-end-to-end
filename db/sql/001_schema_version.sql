create table if not exists schema_version (
    version     text        primary key,
    description text        not null,
    applied_at  timestamptz not null default now(),
    applied_by  text        not null default current_user
);

insert into schema_version (version, description) values
    ('000', 'extensions: pgcrypto, btree_gist, citext'),
    ('001', 'schema_version table')
on conflict (version) do nothing;