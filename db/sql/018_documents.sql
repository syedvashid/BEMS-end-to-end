create table if not exists documents (
  id bigint generated always as identity primary key,
  public_id uuid not null default gen_random_uuid(),
  facility_id bigint not null references facilities (id),
  document_type text not null,
  title text not null,
  description text,
  entity_type text not null,
  entity_public_id uuid not null,
  expiry_date date,
  current_version_no integer not null default 1,
  created_at timestamptz not null default now(), created_by bigint references users (id),
  updated_at timestamptz not null default now(), updated_by bigint references users (id),
  is_active boolean not null default true,
  row_version integer not null default 1,
  constraint uq_documents_public_id unique (public_id),
  constraint uq_documents_facility_id_id unique (facility_id, id),
  constraint ck_documents_rowver check (row_version >= 1),
  constraint ck_documents_type check (document_type in (
    'MANUAL','INVOICE','PURCHASE_ORDER','GRN','WARRANTY_CARD','INSTALLATION_REPORT',
    'ACCEPTANCE_REPORT','SERVICE_REPORT','CALIBRATION_CERTIFICATE','CONTRACT','LICENSE',
    'REGISTRATION_CERTIFICATE','PHOTO','OTHER')),
  constraint ck_documents_title check (btrim(title) <> '' and char_length(title) <= 200),
  constraint ck_documents_description check (description is null or char_length(description) <= 1000),
  constraint ck_documents_entity_type check (entity_type ~ '^[a-z][a-z0-9_]*$' and char_length(entity_type) <= 50),
  constraint ck_documents_version_no check (current_version_no >= 1)
);
create index if not exists ix_documents_entity
  on documents (facility_id, entity_type, entity_public_id) where is_active;
create index if not exists ix_documents_expiry
  on documents (facility_id, expiry_date) where is_active and expiry_date is not null;
drop trigger if exists trg_documents_touch on documents;
create trigger trg_documents_touch before update on documents
  for each row execute function touch_row();
grant select, insert, update on documents to bems_app;
insert into schema_version (version, description)
  values ('018', 'documents') on conflict (version) do nothing;