# MedVoice Portal — Frontend

Next.js clinical portal for the MedVoice Service. Provides authentication, a dashboard for audio consultation management, patient records, and an AI-powered medical assistant — all proxied through a secure API layer to the FastAPI backend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | [Next.js 15](https://nextjs.org/) (Turbopack) |
| Language | TypeScript |
| Database | PostgreSQL via [Drizzle ORM](https://orm.drizzle.team/) |
| Auth | JWT sessions (`jose`) with global middleware |
| UI | [shadcn/ui](https://ui.shadcn.com/) + [Radix UI](https://www.radix-ui.com/) + [Tailwind CSS v4](https://tailwindcss.com/) |
| Icons | [Lucide React](https://lucide.dev/) |
| Data Fetching | [SWR](https://swr.vercel.app/) |
| Unit Tests | [Vitest](https://vitest.dev/) + Testing Library |
| E2E Tests | [Playwright](https://playwright.dev/) |
| Validation | [Zod](https://zod.dev/) |

## Features

- **JWT Authentication** — Sign-in / sign-up with bcrypt password hashing and cookie-based JWT sessions
- **Route Protection** — Global Next.js middleware guards `/dashboard` routes
- **Team Management** — Multi-user teams with roles, invitations, and activity logging
- **MedVoice API Proxy** — Server-side proxy routes forward requests to the FastAPI backend, keeping `BACKEND_URL` hidden from the client
- **Dashboard Pages**
  - **Overview** — System health and database statistics
  - **Upload Consultation** — Upload audio for transcription (with WhisperX model selection)
  - **My Consultations** — Monitor workflow status and view results
  - **Patient Records** — Browse patient data and consultation history
  - **Medical Assistant** — RAG-powered AI chat per patient
- **Responsive Sidebar** — Collapsible navigation with mobile bottom-bar fallback
- **HIPAA Compliance Indicators** — UI badge and audit-ready activity logging

## Getting Started

### Prerequisites

- **Node.js** ≥ 20
- **pnpm** (via corepack: `corepack enable`)
- **PostgreSQL** instance (shared with root project or standalone)

### Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Configure environment
cp .env.example .env
# Edit .env — set POSTGRES_URL, AUTH_SECRET, BACKEND_URL
```

### Database

```bash
# Generate migrations from Drizzle schema
pnpm db:generate

# Run migrations
pnpm db:migrate

# Seed default user and team
pnpm db:seed
```

Default seed credentials:

| Field | Value |
|-------|-------|
| Email | `test@test.com` |
| Password | `admin123` |

### Development

```bash
pnpm dev
# → http://localhost:3000
```

### Docker

```bash
# Using make at root directory (Recommended)
make build
make up
make pgweb

# Or using docker
docker build -f Dockerfile.nextjs -t medvoice-portal .
docker run -p 3000:3000 --env-file .env medvoice-portal
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/medvoice_portal` |
| `AUTH_SECRET` | JWT signing secret (shared with backend) | `random-auth-secret` |
| `BASE_URL` | Frontend origin | `http://localhost:3000` |
| `BACKEND_URL` | MedVoice FastAPI backend URL | `http://localhost:8000` |

## Scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start dev server (Turbopack) |
| `pnpm build` | Production build |
| `pnpm start` | Start production server |
| `pnpm test` | Run unit tests (Vitest) |
| `pnpm e2e-test` | Run E2E tests (Playwright) |
| `pnpm lint` | ESLint |
| `pnpm typecheck` | TypeScript type check |
| `pnpm db:setup` | Interactive `.env` generator |
| `pnpm db:generate` | Generate Drizzle migrations |
| `pnpm db:migrate` | Apply migrations |
| `pnpm db:seed` | Seed database |
| `pnpm db:studio` | Open Drizzle Studio |

## License

MIT
