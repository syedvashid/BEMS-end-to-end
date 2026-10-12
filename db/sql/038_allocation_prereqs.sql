begin;

-- unique (facility_id, id) where missing: needed for composite same-facility FKs
do $$
declare t text;
begin
  foreach t in array array['equipment', 'departments', 'locations'] loop
    if not exists (
      select 1 from pg_index i
       where i.indrelid = t::regclass and i.indisunique and i.indpred is null and i.indnatts = 2
         and (select array_agg(a.attname::text order by k.ord)
                from unnest(i.indkey::int2[]) with ordinality k (attnum, ord)
                join pg_attribute a on a.attrelid = i.indrelid and a.attnum = k.attnum)
             = array['facility_id', 'id']
    ) then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id');
    end if;
  end loop;
end $$;

create table if not exists user_departments (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  user_id bigint not null references users (id),
  department_id bigint not null,
  created_at timestamptz not null default now(),
  created_by bigint references users (id),
  constraint uq_user_departments_public_id unique (public_id),
  constraint uq_user_departments_user_dept unique (user_id, department_id, facility_id),
  constraint fk_user_departments_department foreign key (facility_id, department_id)
    references departments (facility_id, id)
);
create index if not exists ix_user_departments_dept on user_departments (facility_id, department_id);

grant select, insert, delete on user_departments to bems_app;

insert into schema_version (version, description)
  values ('038', 'allocation prerequisites: composite keys, user_departments') on conflict (version) do nothing;
commit;