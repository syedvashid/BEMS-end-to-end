-- 024: location subtree helper (facility-scoped, cycle-safe via UNION). Run as bems_owner.
create index if not exists ix_locations_parent on locations (facility_id, parent_location_id);

create or replace function location_subtree_ids(p_facility_id bigint, p_root_id bigint)
returns setof bigint
language sql stable set search_path = public as $$
  with recursive t(id) as (
    select l.id from locations l
     where l.facility_id = p_facility_id and l.id = p_root_id and l.is_active
    union
    select c.id from locations c join t on c.parent_location_id = t.id
     where c.facility_id = p_facility_id and c.is_active
  )
  select id from t;
$$;
grant execute on function location_subtree_ids(bigint, bigint) to bems_app;

insert into schema_version (version, description)
  values ('024', 'location_subtree_ids function') on conflict (version) do nothing;
