# AI Recruiting Agent

A full-stack recruiting workspace built with Next.js, TypeScript, Tailwind CSS, FastAPI, Supabase PostgreSQL/Auth/Storage, and Sarvam AI.

## What is included

- Recruiter and candidate sign-up/sign-in through Supabase Auth
- Role-based recruiter and candidate workspaces
- Recruiter job creation and candidate browsing/applications
- Private resume upload (PDF, DOCX, TXT), text extraction, and Sarvam resume screening
- English and Hindi interview scheduling
- Browser microphone interviews using Sarvam speech-to-text, Sarvam chat, and Sarvam text-to-speech
- Saved interview transcripts and structured AI reports for human review
- In-app interview notifications and optional SMTP email notifications
- Supabase row-level security policies and a private resume Storage bucket

No credentials are included. Sarvam and Supabase features make real service calls and report configuration/network errors; no fake API responses are used.

## Requirements

- Node.js 20.9 or newer and pnpm 9+
- Python 3.10 or newer
- A Supabase project
- A Sarvam API subscription key for screening and voice interviews

## 1. Configure Supabase

1. Create a Supabase project.
2. Open **SQL Editor** and run [`supabase/migrations/001_initial_schema.sql`](supabase/migrations/001_initial_schema.sql). This creates the application tables, signup profile trigger, RLS policies, and private `resumes` bucket.
3. Copy `.env.example` to `.env.local` in the project root. Fill in your Supabase project URL and publishable (or anon) key. These values are used by the browser Auth client.
4. In `backend/`, copy `.env.example` to `.env`. Set the same Supabase URL and publishable key, the database connection string from **Project Settings → Database**, and the service-role key. Keep the service-role key only in this backend file.
5. Set `SARVAM_API_KEY` in `backend/.env`. The default models can be changed there.

The app uses Supabase email confirmation if it is enabled in your project’s Auth settings. New users should confirm their address before signing in. Recruiter/candidate account type is selected during sign-up.

## 2. Start the FastAPI backend

In a terminal, from the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API docs are at [http://localhost:8000/docs](http://localhost:8000/docs). Check [http://localhost:8000/api/health](http://localhost:8000/api/health) to see which services are configured.

## 3. Start the Next.js application

In a second terminal, from the project root:

```bash
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000), create an account, and choose Recruiter or Candidate. Sign in at `/login`. The dashboard is at `/dashboard`.

## Optional email notifications

Interview reminders are always saved in the app’s notification list. To send an email too, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` in `backend/.env`. Without SMTP settings, the app does not claim to have emailed a candidate.

## Helpful commands

```bash
pnpm lint
pnpm typecheck
pnpm build
```

## Project structure

```text
backend/
  app/                  FastAPI routes, auth, database models, and integrations
  requirements.txt      Python packages
  .env.example          Server-side environment template
src/
  app/                  Landing page, account screens, dashboard, and workflows
  components/           Shared workspace and status UI
  lib/                  Supabase browser client and API helper
supabase/migrations/    Database schema, RLS, trigger, and Storage bucket
```

## Interview audio and reports

The browser records one response at a time (up to 20 seconds) and sends it to the FastAPI backend for Sarvam transcription. Audio bytes are not persisted by this app; transcript turns are stored in Supabase. Sarvam generates the interviewer response and spoken audio. A structured report is generated when the candidate finishes. The report is decision support only; recruiters must review the transcript and evidence and make hiring decisions themselves.

## Important deployment notes

- Deploy the Next.js frontend and FastAPI backend separately, then set `NEXT_PUBLIC_API_URL` and `FRONTEND_URL` to their deployed origins.
- Keep `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `SARVAM_API_KEY`, and SMTP secrets on the backend only.
- This starter has no production rate limiting, malware scanning, audit export, or background job queue. Add these before handling real applicant data at scale.
