-- 026_maintenance_foundation.sql  (run as bems_owner)
-- Phase 5 / 1: unique (facility_id, id) guards, number_sequences, checklist templates + items.

do $$
declare t text;
begin
  foreach t in array array['equipment','equipment_categories','equipment_models','vendors','departments'] loop
    if not exists (
      select 1 from pg_index i
       where i.indrelid = t::regclass
         and i.indisunique and i.indpred is null and i.indexprs is null and i.indnatts = 2
         and (select array_agg(a.attname::text order by a.attname::text)
                from pg_attribute a
               where a.attrelid = i.indrelid and a.attnum = any (i.indkey)) = array['facility_id','id']
    ) then
      execute format('alter table %I add constraint %I unique (facility_id, id)', t, 'uq_' || t || '_facility_id_id');
    end if;
  end loop;
end $$;

create table if not exists number_sequences (
  facility_id   bigint  not null references facilities (id),
  sequence_code text    not null,
  year          integer not null,
  last_value    integer not null default 0,
  primary key (facility_id, sequence_code, year),
  constraint ck_number_sequences_code check (sequence_code ~ '^[A-Z][A-Z0-9_]*$'),
  constraint ck_number_sequences_last check (last_value >= 0 and last_value <= 999999)
);
grant select, insert, update on number_sequences to bems_app;

create table if not exists checklist_templates (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  name text not null,
  description text,
  category_id bigint,
  equipment_model_id bigint,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_checklist_templates_public_id unique (public_id),
  constraint uq_checklist_templates_facility_id_id unique (facility_id, id),
  constraint ck_checklist_templates_rowver check (row_version >= 1),
  constraint ck_checklist_templates_name check (btrim(name) <> ''),
  constraint fk_checklist_templates_category foreign key (facility_id, category_id)
    references equipment_categories (facility_id, id),
  constraint fk_checklist_templates_model foreign key (facility_id, equipment_model_id)
    references equipment_models (facility_id, id)
);
create unique index if not exists ux_checklist_templates_name_active
  on checklist_templates (facility_id, lower(name)) where is_active;
create index if not exists ix_checklist_templates_category on checklist_templates (facility_id, category_id);
create index if not exists ix_checklist_templates_model on checklist_templates (facility_id, equipment_model_id);
drop trigger if exists trg_checklist_templates_touch on checklist_templates;
create trigger trg_checklist_templates_touch before update on checklist_templates
  for each row execute function touch_row();
grant select, insert, update on checklist_templates to bems_app;

create table if not exists checklist_template_items (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  checklist_template_id bigint not null,
  sequence integer not null,
  item_text text not null,
  item_type text not null,
  unit text,
  min_value numeric(14,4),
  max_value numeric(14,4),
  created_at timestamptz not null default now(), created_by bigint references users (id),
  constraint uq_checklist_template_items_public_id unique (public_id),
  constraint uq_checklist_template_items_seq unique (checklist_template_id, sequence),
  constraint ck_checklist_template_items_seq check (sequence > 0),
  constraint ck_checklist_template_items_text check (btrim(item_text) <> ''),
  constraint ck_checklist_template_items_type check (item_type in ('CHECK','MEASUREMENT')),
  constraint ck_checklist_template_items_range check (min_value is null or max_value is null or min_value <= max_value),
  constraint fk_checklist_template_items_template foreign key (facility_id, checklist_template_id)
    references checklist_templates (facility_id, id)
);
grant select, insert, delete on checklist_template_items to bems_app;

insert into schema_version (version, description)
  values ('026', 'maintenance foundation: facility_id+id uniques, number_sequences, checklist templates') on conflict (version) do nothing;
