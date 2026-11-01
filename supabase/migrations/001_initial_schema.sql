-- Run once in Supabase SQL Editor. The API uses Supabase Auth for identity;
-- business data stays behind RLS and is accessed by the FastAPI service.
create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id text primary key, email text not null unique, full_name text not null default '',
  role text not null check (role in ('recruiter','candidate')), phone text,
  created_at timestamptz not null default now()
);
create table if not exists public.jobs (
  id text primary key default gen_random_uuid()::text, recruiter_id text not null references public.profiles(id) on delete cascade,
  title text not null, department text not null default '', location text not null default 'Remote',
  employment_type text not null default 'Full-time', description text not null, requirements jsonb not null default '[]'::jsonb,
  status text not null default 'published' check (status in ('draft','published','closed')), created_at timestamptz not null default now()
);
create index if not exists jobs_recruiter_created_idx on public.jobs(recruiter_id,created_at desc);
create table if not exists public.applications (
  id text primary key default gen_random_uuid()::text, job_id text not null references public.jobs(id) on delete cascade,
  candidate_id text not null references public.profiles(id) on delete cascade,
  status text not null default 'applied' check (status in ('applied','screening','interview','offer','rejected')),
  resume_filename text, resume_path text, resume_text text, screening jsonb, applied_at timestamptz not null default now(),
  constraint uq_job_candidate unique(job_id,candidate_id)
);
create index if not exists applications_candidate_idx on public.applications(candidate_id,applied_at desc);
create table if not exists public.interviews (
  id text primary key default gen_random_uuid()::text, application_id text not null unique references public.applications(id) on delete cascade,
  scheduled_at timestamptz, language text not null default 'en-IN' check (language in ('en-IN','hi-IN')),
  status text not null default 'scheduled' check (status in ('scheduled','in_progress','completed','cancelled')),
  evaluation jsonb, started_at timestamptz, completed_at timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.interview_turns (
  id text primary key default gen_random_uuid()::text, interview_id text not null references public.interviews(id) on delete cascade,
  speaker text not null check (speaker in ('interviewer','candidate')), content text not null, language_code text,
  created_at timestamptz not null default now()
);
create index if not exists interview_turns_order_idx on public.interview_turns(interview_id,created_at);
create table if not exists public.notifications (
  id text primary key default gen_random_uuid()::text, user_id text not null references public.profiles(id) on delete cascade,
  title text not null, body text not null, link text, read boolean not null default false, created_at timestamptz not null default now()
);
create index if not exists notifications_user_created_idx on public.notifications(user_id,created_at desc);

-- Supabase Auth signup creates the matching app profile from user metadata.
create or replace function public.handle_new_auth_user() returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles(id,email,full_name,role) values (new.id::text, coalesce(new.email,''), coalesce(new.raw_user_meta_data->>'full_name',''),
    case when new.raw_user_meta_data->>'role' = 'recruiter' then 'recruiter' else 'candidate' end)
  on conflict (id) do update set email=excluded.email;
  return new;
end; $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute procedure public.handle_new_auth_user();

-- Private bucket for resumes. The API creates short-lived signed download links.
insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types) values ('resumes','resumes',false,8388608,array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain']) on conflict (id) do update set public=false,file_size_limit=8388608;

-- Row-level security remains enabled even though FastAPI also enforces ownership.
alter table public.profiles enable row level security;
alter table public.jobs enable row level security;
alter table public.applications enable row level security;
alter table public.interviews enable row level security;
alter table public.interview_turns enable row level security;
alter table public.notifications enable row level security;

drop policy if exists profiles_read_self on public.profiles; create policy profiles_read_self on public.profiles for select to authenticated using (id=auth.uid()::text);
drop policy if exists profiles_update_self on public.profiles; create policy profiles_update_self on public.profiles for update to authenticated using (id=auth.uid()::text) with check (id=auth.uid()::text);
drop policy if exists jobs_public_read on public.jobs; create policy jobs_public_read on public.jobs for select to anon,authenticated using (status='published' or recruiter_id=auth.uid()::text);
drop policy if exists jobs_recruiter_write on public.jobs; create policy jobs_recruiter_write on public.jobs for all to authenticated using (recruiter_id=auth.uid()::text and exists(select 1 from public.profiles p where p.id=auth.uid()::text and p.role='recruiter')) with check (recruiter_id=auth.uid()::text and exists(select 1 from public.profiles p where p.id=auth.uid()::text and p.role='recruiter'));
drop policy if exists applications_participant_read on public.applications; create policy applications_participant_read on public.applications for select to authenticated using (candidate_id=auth.uid()::text or exists(select 1 from public.jobs j where j.id=job_id and j.recruiter_id=auth.uid()::text));
drop policy if exists applications_candidate_insert on public.applications; create policy applications_candidate_insert on public.applications for insert to authenticated with check (candidate_id=auth.uid()::text and exists(select 1 from public.profiles p where p.id=auth.uid()::text and p.role='candidate'));
drop policy if exists applications_recruiter_update on public.applications; create policy applications_recruiter_update on public.applications for update to authenticated using (exists(select 1 from public.jobs j where j.id=job_id and j.recruiter_id=auth.uid()::text)) with check (exists(select 1 from public.jobs j where j.id=job_id and j.recruiter_id=auth.uid()::text));
drop policy if exists interviews_participant_read on public.interviews; create policy interviews_participant_read on public.interviews for select to authenticated using (exists(select 1 from public.applications a join public.jobs j on j.id=a.job_id where a.id=application_id and (a.candidate_id=auth.uid()::text or j.recruiter_id=auth.uid()::text)));
drop policy if exists interview_turns_participant_read on public.interview_turns; create policy interview_turns_participant_read on public.interview_turns for select to authenticated using (exists(select 1 from public.interviews i join public.applications a on a.id=i.application_id join public.jobs j on j.id=a.job_id where i.id=interview_id and (a.candidate_id=auth.uid()::text or j.recruiter_id=auth.uid()::text)));
drop policy if exists notifications_read_self on public.notifications; create policy notifications_read_self on public.notifications for select to authenticated using (user_id=auth.uid()::text);
drop policy if exists notifications_update_self on public.notifications; create policy notifications_update_self on public.notifications for update to authenticated using (user_id=auth.uid()::text) with check (user_id=auth.uid()::text);

-- Supabase Storage read policies keep uploaded resumes private. FastAPI uses the service role for upload/signing.
drop policy if exists resumes_owner_read on storage.objects; create policy resumes_owner_read on storage.objects for select to authenticated using (bucket_id='resumes' and (storage.foldername(name))[1]=auth.uid()::text);
drop policy if exists resumes_owner_insert on storage.objects; create policy resumes_owner_insert on storage.objects for insert to authenticated with check (bucket_id='resumes' and (storage.foldername(name))[1]=auth.uid()::text);
