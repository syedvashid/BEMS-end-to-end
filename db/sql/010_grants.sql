grant usage on schema public to bems_app;

-- Soft-delete tables: no DELETE
grant select, insert, update on facilities, users, roles, user_facility_roles to bems_app;
-- Seeded by SQL only
grant select on permissions to bems_app;
-- Replaced as a set by PUT
grant select, insert, delete on role_permissions to bems_app;
-- Append-only
grant select, insert on audit_log to bems_app;
revoke update, delete, truncate on audit_log from bems_app;

grant select on schema_version to bems_app;
grant usage, select on all sequences in schema public to bems_app;

insert into schema_version (version, description)
values ('010', 'grants for bems_app') on conflict (version) do nothing;