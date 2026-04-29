create table if not exists public.push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(id) on delete cascade,
  expo_push_token text not null unique,
  platform text check (platform in ('ios', 'android')),
  device_id text,
  app_version text,
  is_active boolean not null default true,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.admin_users (
  user_id uuid primary key,
  email text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.notification_campaigns (
  id uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null,
  title text not null,
  body text not null,
  image_url text,
  image_storage_path text,
  data jsonb not null default '{}'::jsonb,
  target text not null default 'all',
  status text not null default 'queued',
  total_tokens integer not null default 0,
  sent_count integer not null default 0,
  failed_count integer not null default 0,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

create table if not exists public.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references public.notification_campaigns(id) on delete cascade,
  push_token_id uuid references public.push_tokens(id) on delete set null,
  expo_push_token text not null,
  status text not null,
  expo_ticket_id text,
  error text,
  created_at timestamptz not null default now()
);

create index if not exists push_tokens_active_idx on public.push_tokens(is_active);
create index if not exists notification_campaigns_created_at_idx on public.notification_campaigns(created_at desc);
create index if not exists notification_deliveries_campaign_id_idx on public.notification_deliveries(campaign_id);

alter table public.notification_campaigns
  add column if not exists image_storage_path text;
