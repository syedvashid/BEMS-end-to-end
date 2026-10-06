-- Attach to every table that has updated_at + row_version.
-- Also freezes id, public_id and created_at so they cannot change on UPDATE.
create or replace function touch_row() returns trigger
language plpgsql as $$
begin
    new.id          := old.id;
    new.public_id   := old.public_id;
    new.created_at  := old.created_at;
    new.updated_at  := now();
    new.row_version := old.row_version + 1;
    return new;
end;
$$;

insert into schema_version (version, description)
values ('002', 'common trigger function touch_row()')
on conflict (version) do nothing;