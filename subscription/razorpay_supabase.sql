alter table public.user_profiles
  add column if not exists razorpay_customer_id text default null,
  add column if not exists razorpay_subscription_id text default null;

create table if not exists public.subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(id) on delete cascade,
  app_plan text not null check (app_plan in ('weekly', 'monthly')),
  razorpay_plan_id text not null,
  razorpay_subscription_id text not null unique,
  razorpay_customer_id text default null,
  razorpay_status text not null default 'created',
  current_start timestamptz default null,
  current_end timestamptz default null,
  cancelled_at timestamptz default null,
  raw_payload jsonb default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_subscriptions_user_updated
  on public.subscriptions (user_id, updated_at desc);

create index if not exists idx_subscriptions_user_status
  on public.subscriptions (user_id, razorpay_status);

create table if not exists public.razorpay_webhook_events (
  event_id text primary key,
  event_name text not null,
  payload jsonb not null,
  processed_at timestamptz not null default now()
);

alter table public.subscriptions enable row level security;
alter table public.razorpay_webhook_events enable row level security;

drop policy if exists "Users read own subscriptions" on public.subscriptions;
create policy "Users read own subscriptions"
  on public.subscriptions for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "No direct client writes to subscriptions" on public.subscriptions;
create policy "No direct client writes to subscriptions"
  on public.subscriptions for all
  to authenticated
  using (false)
  with check (false);

drop policy if exists "No direct client access to razorpay webhooks" on public.razorpay_webhook_events;
create policy "No direct client access to razorpay webhooks"
  on public.razorpay_webhook_events for all
  to authenticated
  using (false)
  with check (false);
