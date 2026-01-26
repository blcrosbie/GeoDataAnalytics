create extension if not exists "pgcrypto";

create schema if not exists app;

create or replace function app.current_user_id()
returns uuid
language sql
stable
as $$
select nullif(current_setting('app.user_id', true), '')::uuid;
$$;

create or replace function app.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.profiles (
  user_id uuid primary key,
  display_name text,
  handle text unique,
  bio text,
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.uploads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  source_type text not null,
  source_uri text,
  status text not null default 'pending',
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.layers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  name text not null,
  description text,
  visibility text not null default 'private' check (visibility in ('private', 'public', 'unlisted')),
  source_upload_id uuid references public.uploads(id) on delete set null,
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  event_type text not null,
  prompt text,
  tokens_in integer not null default 0,
  tokens_out integer not null default 0,
  revenue_cents integer not null default 0,
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.credits_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  delta numeric(18, 6) not null,
  reason text not null,
  source_event_id uuid references public.usage_events(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.contributions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  layer_id uuid references public.layers(id) on delete set null,
  source_upload_id uuid references public.uploads(id) on delete set null,
  geoid varchar(64),
  year integer,
  contribution_type varchar(32) not null,
  record_count integer default 1,
  attributes_added text[],
  quality_score numeric(3, 2) default 1.0,
  batch_id uuid,
  source_file text,
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.data_queries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  geoid_pattern varchar(128),
  attribute_keys text[],
  query_type varchar(32),
  result_count integer,
  query_duration_ms integer,
  api_endpoint varchar(128),
  attributes jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.trending_attributes (
  id uuid primary key default gen_random_uuid(),
  year integer not null,
  month integer not null,
  attribute_key varchar(128) not null,
  query_count integer default 0,
  unique_users integer default 0,
  contribution_count integer default 0,
  trending_score numeric(10, 2) default 0.0,
  created_at timestamptz not null default now(),
  unique(year, month, attribute_key)
);

create table if not exists public.reputation_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  event_type varchar(32) not null,
  points_awarded integer not null,
  reason text,
  reference_id uuid,
  created_at timestamptz not null default now()
);

create index if not exists idx_uploads_user_id on public.uploads(user_id);
create index if not exists idx_uploads_attributes on public.uploads using gin (attributes);
create index if not exists idx_layers_user_id on public.layers(user_id);
create index if not exists idx_layers_attributes on public.layers using gin (attributes);
create index if not exists idx_usage_events_user_id on public.usage_events(user_id);
create index if not exists idx_usage_events_created_at on public.usage_events(created_at);
create index if not exists idx_usage_events_attributes on public.usage_events using gin (attributes);
create index if not exists idx_credits_ledger_user_id on public.credits_ledger(user_id);
create index if not exists idx_contributions_user_id on public.contributions(user_id);
create index if not exists idx_contributions_layer_id on public.contributions(layer_id);
create index if not exists idx_contributions_geoid_year on public.contributions(geoid, year);
create index if not exists idx_data_queries_user_id on public.data_queries(user_id);
create index if not exists idx_data_queries_created_at on public.data_queries(created_at);
create index if not exists idx_trending_attributes_score on public.trending_attributes(trending_score desc, year, month);
create index if not exists idx_reputation_events_user_id on public.reputation_events(user_id);

alter table public.geographic_boundaries
  drop constraint if exists fk_geographic_boundaries_layer,
  drop constraint if exists fk_geographic_boundaries_upload;

alter table public.geographic_boundaries
  add constraint fk_geographic_boundaries_layer
  foreign key (layer_id) references public.layers(id) on delete set null,
  add constraint fk_geographic_boundaries_upload
  foreign key (source_upload_id) references public.uploads(id) on delete set null;

alter table public.geographic_data
  drop constraint if exists fk_geographic_data_layer,
  drop constraint if exists fk_geographic_data_upload;

alter table public.geographic_data
  add constraint fk_geographic_data_layer
  foreign key (layer_id) references public.layers(id) on delete set null,
  add constraint fk_geographic_data_upload
  foreign key (source_upload_id) references public.uploads(id) on delete set null;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function app.set_updated_at();

drop trigger if exists uploads_set_updated_at on public.uploads;
create trigger uploads_set_updated_at
before update on public.uploads
for each row execute function app.set_updated_at();

drop trigger if exists layers_set_updated_at on public.layers;
create trigger layers_set_updated_at
before update on public.layers
for each row execute function app.set_updated_at();

alter table public.profiles enable row level security;
alter table public.uploads enable row level security;
alter table public.layers enable row level security;
alter table public.usage_events enable row level security;
alter table public.credits_ledger enable row level security;
alter table public.contributions enable row level security;
alter table public.data_queries enable row level security;
alter table public.trending_attributes enable row level security;
alter table public.reputation_events enable row level security;

alter table public.profiles force row level security;
alter table public.uploads force row level security;
alter table public.layers force row level security;
alter table public.usage_events force row level security;
alter table public.credits_ledger force row level security;
alter table public.contributions force row level security;
alter table public.data_queries force row level security;
alter table public.trending_attributes force row level security;
alter table public.reputation_events force row level security;

drop policy if exists profiles_owner on public.profiles;
create policy profiles_owner on public.profiles
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists uploads_owner on public.uploads;
create policy uploads_owner on public.uploads
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists layers_owner on public.layers;
create policy layers_owner on public.layers
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists usage_events_owner on public.usage_events;
create policy usage_events_owner on public.usage_events
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists credits_ledger_owner on public.credits_ledger;
create policy credits_ledger_owner on public.credits_ledger
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists contributions_owner on public.contributions;
create policy contributions_owner on public.contributions
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists data_queries_owner on public.data_queries;
create policy data_queries_owner on public.data_queries
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists reputation_events_owner on public.reputation_events;
create policy reputation_events_owner on public.reputation_events
  using (user_id = app.current_user_id())
  with check (user_id = app.current_user_id());

drop policy if exists trending_attributes_read on public.trending_attributes;
create policy trending_attributes_read on public.trending_attributes
  for select using (true);

drop policy if exists trending_attributes_write on public.trending_attributes;
create policy trending_attributes_write on public.trending_attributes
  for insert, update, delete
  using (app.current_user_id() is not null)
  with check (app.current_user_id() is not null);
