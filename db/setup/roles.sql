-- One-time setup. Run as superuser against bems_dev_new.
alter database bems_dev_new owner to bems_owner;   -- owner also owns schema public on PG15+
revoke connect on database bems_dev_new from public;
grant connect on database bems_dev_new to bems_owner, bems_app;

alter role bems_owner nosuperuser nocreatedb nocreaterole nobypassrls login;
alter role bems_app   nosuperuser nocreatedb nocreaterole nobypassrls login;

grant usage on schema public to bems_app;