-- Run this in Supabase Dashboard -> SQL Editor
-- Creates the "projects" table used by the Freelance Manager app.

create table if not exists public.projects (
    id               bigint generated always as identity primary key,
    client_name      text not null,
    project_name     text not null,
    project_amount   numeric(12, 2) not null default 0 check (project_amount >= 0),
    paid_amount      numeric(12, 2) not null default 0 check (paid_amount >= 0),
    project_status   text not null default 'Planning'
                        check (project_status in ('Planning', 'In Progress', 'On Hold', 'Completed', 'Cancelled')),
    is_completed     boolean not null default false,
    paid_via         text not null default 'Not Paid'
                        check (paid_via in ('UPI', 'Net Banking', 'Card', 'Cash', 'Other', 'Not Paid')),
    invoice_number   text unique,
    created_at       timestamptz not null default now()
);

-- Keep lookups by recency and by invoice number fast.
create index if not exists projects_created_at_idx on public.projects (created_at desc);
create index if not exists projects_invoice_number_idx on public.projects (invoice_number);

-- Row Level Security -------------------------------------------------------
-- This app talks to Supabase using the SERVICE ROLE key from the Flask
-- backend only (never from a browser). The service role key bypasses RLS
-- entirely, so RLS is not what protects this data - the app's own login
-- screen and the fact that the service key never reaches the browser are
-- what protect it.
--
-- Even so, enabling RLS with no public-facing policies is good defense in
-- depth: if the ANON key were ever leaked or accidentally used client-side,
-- it would not be able to read or write anything.
alter table public.projects enable row level security;

-- No policies are created for "anon" or "authenticated" roles on purpose,
-- so only the service role (used by the Flask server) can access this
-- table. Do NOT add a permissive "USING (true)" policy for anon/authenticated
-- unless you specifically want this data reachable with the public anon key.
