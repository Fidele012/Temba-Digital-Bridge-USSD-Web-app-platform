# Temba Digital Bridge

> A bilingual (English / Kinyarwanda) digital platform that connects Rwandan communities to water service providers through a web interface and a USSD feature-phone channel — so every citizen, regardless of smartphone access, can report water issues, book appointments, and track resolutions in real time.

![Tests](https://img.shields.io/badge/tests-55%2F55%20passing-2E7D32?style=flat-square)
![Coverage](https://img.shields.io/badge/coverage-57%25-0097A7?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-1565C0?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/licence-ALU%20Capstone-0A2540?style=flat-square)

---

![Temba Digital Bridge — Landing Page](docs/screenshots/Landing.png)

> **[GitHub Repository](https://github.com/Fidele012/Temba_Digital_Bridge.git)**

---

## Table of Contents

1. [Project Description](#1-project-description)
2. [Key Features](#2-key-features)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Demo Video](#demo-video)
6. [Testing](#testing)
7. [Designs](#5-designs)
   - [Figma Prototype](#51-figma-prototype)
   - [App Interface Screenshots](#52-app-interface-screenshots)
   - [System Architecture Diagram](#53-system-architecture-diagram)
8. [Getting Started](#6-getting-started)
   - [Prerequisites](#61-prerequisites)
   - [Clone the Repository](#62-clone-the-repository)
   - [Backend Setup](#63-backend-setup)
   - [Frontend Setup](#64-frontend-setup)
   - [Africa's Talking USSD Setup](#65-africas-talking-ussd-setup)
9. [Environment Variables](#7-environment-variables)
10. [Deployment Plan](#8-deployment-plan)
11. [API Reference](#9-api-reference)
12. [Project Structure](#10-project-structure)
13. [Database Schema](#11-database-schema)

---

## 1. Project Description

### Problem Statement

Access to clean water is a fundamental human right, yet millions of Rwandans still face daily challenges with water supply disruption, pipe bursts, contamination, and billing errors. The gap between affected communities and the water service providers responsible for resolving those issues is wide — residents have no reliable, structured way to report problems, track progress, or hold providers accountable. Meanwhile, providers lack visibility into their service quality and response times.

### What Temba Digital Bridge Does

**Temba Digital Bridge** (Kinyarwanda: *temba* — "to push forward") is a full-stack civic-tech platform that bridges this gap through four complementary components.

**Community Web Platform** — A responsive website where community members can:

- Register and set up a profile with their Rwanda administrative location (province → district → sector → cell → village)
- Submit detailed water issue reports with category, urgency level, and optional photos
- Book service appointments directly with water providers
- Track any submitted issue in real time using a unique reference code (e.g. `RPT-20260614-K7M3`)
- Receive in-app and SMS notifications at every stage of resolution
- Verify whether a provider's resolution actually fixed their problem

**USSD Feature-Phone Channel** — Accessible by dialling `*384*36640#` on any basic mobile phone, no internet required. Community members can:

- Register a Temba account entirely via feature phone, navigating Rwanda's full five-level administrative hierarchy through numbered menus
- Report water issues by selecting category and urgency from paginated menus
- Check the status of previously submitted reports
- Receive an SMS confirmation with a unique tracking code after every submission

**Provider Dashboard** — Water service organisations (WASAC, IRIBA, Pro Water Rwanda, and others) access a dedicated dashboard to:

- View all reports and service requests assigned to their organisation
- Update report status through a defined workflow (Acknowledged → Under Review → In Progress → Resolution Submitted)
- Manage team members (Supervisors, Regional Managers, Executives) with role-based access
- View SLA deadlines and receive escalation alerts when response times are breached
- Respond to appointment bookings and propose alternative times
- Set and manage availability so community members can book appropriate slots

**Admin Panel** — Platform administrators can:

- Approve or reject provider registrations
- Publish announcements and alerts to the platform
- Monitor platform-wide analytics (total reports, resolution rates, SLA compliance)
- View a full audit trail of every action taken on the platform

### What Makes This Unique

Unlike generic complaint portals, Temba is built specifically for Rwanda's administrative geography. The USSD registration flow contains the complete Rwanda administrative hierarchy — all 5 provinces, 30 districts, ~416 sectors, ~2,148 cells, and over 14,800 villages — presented as numbered paginated menus. This means a farmer in a rural cell with no smartphone can register and file a report in the same system as an urban professional using the web app.

The platform enforces a structured **accountability loop**: a report is not "closed" by the provider alone. The community member who submitted it must verify that the issue was genuinely resolved. If they dispute the resolution, the case escalates automatically — first to a supervisor, then a regional manager, then an executive — with SMS alerts at each level and SLA deadlines tracked per category (contamination and pipe bursts: 4-hour SLA; no supply: 24 hours; other issues: 72 hours).

The platform is also fully **bilingual**. Every USSD menu, every SMS notification, and every in-app label is available in both English and Kinyarwanda, toggled by the user's language preference — making the system genuinely accessible to all Rwandans.

### Target Users

| User Type | Access Method | Primary Need |
| --- | --- | --- |
| Community Member (urban) | Web platform | File reports, book appointments, track issues |
| Community Member (rural) | USSD `*384*36640#` | File reports, receive SMS tracking codes |
| Water Provider Staff | Web dashboard | Manage reports, update status, respond to appointments |
| Platform Admin | Web admin panel | Approve providers, publish announcements, monitor health |

---

## 2. Key Features

### Community

- Bilingual interface — English and Kinyarwanda on all USSD menus, SMS messages, and web UI
- Five-level Rwanda location picker (province → district → sector → cell → village) on both web and USSD
- Issue reporting with 8 categories (contamination, pipe burst, low pressure, no supply, water quality, billing, meter, other) and 4 urgency levels
- Public tracking page — enter a code and see full status, no account needed
- Service request submission (new water connection, truck delivery, meter support, inspection)
- Appointment booking with provider availability calendar
- Full report history with status timeline
- Resolution verification — community confirms fix before case closes
- SMS notifications for every status change

### Provider

- Organisation dashboard with paginated report inbox, filterable by status and urgency
- SLA countdown indicators — visual warnings before deadlines breach
- Team management — add staff with Supervisor / Regional Manager / Executive roles
- Appointment calendar management with reschedule proposal flow
- Service area and availability configuration
- Members' requested services management
- Alerts and announcements publishing

### Platform

- JWT authentication with 15-minute access tokens and 7-day refresh tokens
- Bcrypt-hashed passwords (web) and 4-digit PINs (USSD)
- Celery-powered background job queue for SLA checks and escalations
- MinIO (S3-compatible) file storage for report media attachments
- Audit trail — every status change and user action is logged
- Rate limiting on authentication endpoints (10 req/min)
- Sentry error monitoring integration
- Language switching between English and Kinyarwanda

---

## 3. System Architecture

```text
┌──────────────────────┐    ┌────────────────────────┐
│   Community Web App  │    │  Provider Web Dashboard │
│  (temba-v2/*.html)   │    │  (temba-v2/dashboard-  │
│   Vanilla JS / CSS   │    │   provider.html)        │
└──────────┬───────────┘    └───────────┬────────────┘
           │  REST API (JWT)             │  REST API (JWT)
           ▼                             ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend  :8000                  │
│  /api/v1/auth  /reports  /appointments               │
│  /providers    /track    /notifications              │
│  /ussd/callback (Africa's Talking POST)              │
└──────┬──────────────────┬──────────────┬────────────┘
       │                  │              │
  ┌────▼────┐       ┌─────▼────┐   ┌────▼──────┐
  │PostgreSQL│       │  Redis   │   │   MinIO   │
  │   :5432  │       │  :6379   │   │   :9000   │
  │(primary  │       │(task     │   │(file      │
  │  data)   │       │ queue +  │   │ storage)  │
  └──────────┘       │  cache)  │   └───────────┘
                     └─────┬────┘
                           │
                     ┌─────▼────┐
                     │  Celery  │
                     │  Worker  │
                     │(SLA jobs)│
                     └──────────┘

Feature Phone User
       │
  dials *384*36640#
       │
  ┌────▼─────────────┐     ┌──────────────────────┐
  │ Africa's Talking │────▶│  ngrok HTTPS tunnel  │
  │  USSD Gateway    │     │  → /api/v1/ussd/     │
  └──────────────────┘     │    callback          │
                           └──────────────────────┘
```

---

## 4. Technology Stack

| Layer | Technology | Version |
| --- | --- | --- |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | — |
| **Backend Framework** | FastAPI | 0.111.0 |
| **Runtime** | Python | 3.11 |
| **ORM** | SQLAlchemy (async) | 2.0.30 |
| **Database** | PostgreSQL | 16 |
| **Cache / Queue Broker** | Redis | 7 |
| **Background Workers** | Celery | 5.4.0 |
| **Task Monitoring** | Flower | 2.0.1 |
| **File Storage** | MinIO (S3-compatible) | latest |
| **Authentication** | JWT via python-jose | 3.3.0 |
| **Password Hashing** | passlib + bcrypt | 1.7.4 |
| **Schema Migrations** | Alembic | 1.13.1 |
| **Validation** | Pydantic v2 | 2.7.1 |
| **USSD / SMS** | Africa's Talking SDK | 1.2.5 |
| **Email** | Gmail SMTP via emails | 0.6.0 |
| **Containerisation** | Docker + Docker Compose | — |
| **USSD Tunnel (dev)** | ngrok | — |
| **Monitoring** | Sentry | 2.2.0 |
| **Logging** | structlog | 24.1.0 |

---

## Demo Video

A full technical walkthrough demonstrating the complete Temba Digital Bridge system — USSD feature-phone flow, web dashboard, chatbot, and provider management.

> **[Watch the Demo Video →](https://youtu.be/YOUR_VIDEO_ID_HERE)**
>
> The video covers: account registration (web + USSD), submitting a water issue report, the provider dashboard SLA indicators, the AI-powered chatbot routing users to the right water provider, and the end-to-end accountability loop from report to verified resolution.

---

## Testing

The full test suite runs 55 tests across 7 modules and passes in under 64 seconds with zero failures.

```bash
cd temba-backend
pytest tests/ -v --tb=short --cov=app --cov-report=term-missing
```

### Results: 55/55 passed — 57% coverage — 63.53s

| Suite | Tests | Focus |
| --- | --- | --- |
| `test_auth.py` | 6 | Registration, login, JWT, password change |
| `test_reports.py` | 3 | Report creation, data isolation, access control |
| `test_appointments.py` | 2 | Book → approve flow, reschedule |
| `test_service_requests.py` | 3 | Create, list own, provider status update |
| `test_security.py` | 11 | JWT boundary, RBAC, input validation, SQL injection |
| `test_edge_cases.py` | 12 | Boundary values, coordinates, all enums, Unicode names |
| `test_ussd.py` | 18 | Full bilingual USSD flows via AT callback simulation |

Four distinct testing strategies are used:

- **Unit** — each endpoint tested in isolation with SQLite in-memory + FakeRedis
- **Integration** — multi-step workflows (book → approve, create → update status) through the full ASGI stack
- **Security** — JWT forgery, RBAC enforcement, weak passwords, SQL injection, data isolation
- **Functional / USSD** — simulated Africa's Talking POST requests for 18 distinct USSD navigation paths

For the full coverage report with individual test descriptions, see [`docs/testing-report.html`](docs/testing-report.html).

---

## 5. Designs

### 5.1 Figma Prototype

The complete UI design for all 25 screens was created in Figma as a single-page interactive prototype. The design follows a consistent style guide:

- **Primary colour**: `#1E6B45` (Temba Green)
- **Accent colour**: `#F5A623` (Temba Amber)
- **Typography**: Inter (headings) + Source Sans Pro (body)
- **Corner radius**: 8px for cards, 4px for inputs
- **Spacing grid**: 8px base unit

[View the interactive Figma prototype →](https://www.figma.com/proto/6MxzM5aUBE9u9apc2xAzdU/Temba-Digital-Bridge-%E2%80%94-Figma-Design?node-id=5-879&t=5w10wxNi0gQWENDH-1)

#### Screen Map — All 22 Screens

The screens are organised into four user flows on a single Figma page.

#### Row 1 — Authentication & Onboarding (6 screens)

| Screen | File | Description |
| --- | --- | --- |
| Landing Page | `Landing` | Hero section, public issue tracker, features overview |
| Sign In | `Signin` | Email and password login for all roles |
| Sign Up — Community | `Signup_community` | Community member registration with location picker |
| Sign Up — Provider | `Signup_water_provider` | Water organisation registration form |
| Reset Password | `Reset_Password` | Email-based password reset flow |
| Language Switching | `Language_switching` | EN ↔ Kinyarwanda language toggle UI |

#### Row 2 — Community Portal (10 screens)

| Screen | File | Description |
| --- | --- | --- |
| Community Dashboard | `Community_member_portal` | Overview cards, quick actions, notification feed |
| Submit Report | `Community_report` | Report category, urgency, description, photo upload |
| Report History | `History` | Full list of submitted reports with status badges |
| Individual Accountability | `Accountability_individual` | Single report timeline, provider updates, verify button |
| Water Quality Report | `Water_quality` | Dedicated water quality issue submission |
| Service Request | `Service_request` | New service request form (connection, truck, meter) |
| Service Requested | `Service_requested` | Confirmation screen after service request submitted |
| Book Appointment | `Appointment_booking` | Provider picker, calendar, available time slots |
| Booked Appointments | `Appointments_booked` | List of upcoming and past appointments |
| Browse Providers | `Providers` | Directory of approved water service providers |

#### Row 3 — Provider Portal (4 screens)

| Screen | File | Description |
| --- | --- | --- |
| Provider Dashboard | `Water_provider_portal` | Stats cards, recent activity, SLA indicators |
| Reports Inbox | `Reports_inbox` | Paginated report list with filters and status controls |
| Member Services | `Members_requested_services` | Service requests submitted by community members |
| Availability Management | `My_availability` | Set working days, hours, and blackout dates |

#### Row 4 — Admin & Shared (2 screens)

| Screen | File | Description |
| --- | --- | --- |
| Alerts & Announcements | `Alerts_Announcements` | View platform-wide alerts and notices |
| Publish Announcement | `Announcements_publishing` | Admin/provider announcement publishing form |

---

### 5.2 App Interface Screenshots

All screenshots below are taken from the live running application.

---

#### Authentication & Onboarding

##### Landing Page

Hero section with public issue tracker and feature highlights.

![Landing Page](docs/screenshots/Landing.png)

---

##### Sign In

Secure login for community members, providers, and admins.

![Sign In](docs/screenshots/Signin.png)

---

##### Sign Up — Community Member

Registration form with Rwanda five-level location picker.

![Sign Up Community](docs/screenshots/Signup_community.png)

---

##### Sign Up — Water Provider

Organisation registration and service category selection.

![Sign Up Provider](docs/screenshots/Signup_water_provider.png)

---

##### Reset Password

Email-based password recovery flow.

![Reset Password](docs/screenshots/Reset_Password.png)

---

##### Language Switching

Toggle between English and Kinyarwanda across the entire interface.

![Language Switching](docs/screenshots/Language_switching.png)

---

#### Community Portal

##### Community Dashboard

Central hub showing active reports, appointments, and quick-action cards.

![Community Dashboard](docs/screenshots/Community_member_portal.png)

---

##### Submit a Report

Water issue reporting with category, urgency level, description, and optional photo upload.

![Submit Report](docs/screenshots/Community_report.png)

---

##### Report History

Complete list of all submitted reports with real-time status badges and tracking codes.

![Report History](docs/screenshots/History.png)

---

##### Individual Report Accountability

Detailed view of a single report: full status timeline, provider notes, and community verification button.

![Individual Accountability](docs/screenshots/Accountability_individual.png)

---

##### Water Quality Report

Dedicated submission form for water quality and contamination issues.

![Water Quality](docs/screenshots/Water_quality.png)

---

##### Service Request

Submit a formal service request (new water connection, tank delivery, meter support, or inspection).

![Service Request](docs/screenshots/Service_request.png)

---

##### Service Request Submitted

Confirmation screen after a service request is successfully submitted, showing the reference number.

![Service Requested](docs/screenshots/Service_requested.png)

---

##### Book an Appointment

Browse providers, select a date on the availability calendar, and choose a time slot.

![Appointment Booking](docs/screenshots/Appointment_booking.png)

---

##### My Appointments

Upcoming and past appointments with status indicators and reschedule options.

![Appointments Booked](docs/screenshots/Appointments_booked.png)

---

##### Browse Providers

Directory of all approved water service providers with service categories and coverage areas.

![Providers](docs/screenshots/Providers.png)

---

##### Member Requested Services

Full list of service requests the community member has submitted.

![Members Requested Services](docs/screenshots/Members_requested_services.png)

---

#### Provider Portal

##### Provider Dashboard

Organisation command centre with statistics, SLA indicators, and recent activity.

![Provider Dashboard](docs/screenshots/Water_provider_portal.png)

---

##### Reports Inbox

Paginated queue of all incoming reports assigned to the provider, with status filters and urgency indicators.

![Reports Inbox](docs/screenshots/Reports_inbox.png)

---

##### Availability Management

Set working days, working hours, maximum daily appointments, and blackout dates.

![My Availability](docs/screenshots/My_availability.png)

---

#### Admin & Shared

##### Alerts & Announcements

Platform-wide alerts, notices, and announcements visible to all users.

![Alerts Announcements](docs/screenshots/Alerts_Announcements.png)

---

##### Publish Announcement

Admin and provider form to draft and publish announcements to the platform.

![Announcements Publishing](docs/screenshots/Announcements_publishing.png)

---

### 5.3 System Architecture Diagram

The ASCII diagram in Section 3 shows the full architecture. For a visual version, draw the same diagram using [draw.io](https://app.diagrams.net), export as PNG, and save to `docs/diagrams/architecture.png`.

![System Architecture](docs/diagrams/architecture.png)

---

## 6. Getting Started

### 6.1 Prerequisites

Install the following tools before starting. Each link goes to the official download page.

| Tool | Version | Purpose |
| --- | --- | --- |
| [Python](https://www.python.org/downloads/) | 3.11 or 3.12 | Backend runtime |
| [PostgreSQL](https://www.postgresql.org/download/) | 16 | Primary database |
| [Redis](https://redis.io/download/) | 7 | Task queue + cache |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | latest | Run services (recommended) |
| [ngrok](https://ngrok.com/download) | latest | USSD tunnel (development) |
| [Git](https://git-scm.com/downloads) | latest | Clone the repo |
| A modern browser | — | Access the web app |

> **Tip:** If you have Docker Desktop installed you do not need to install PostgreSQL or Redis separately — Docker will run them as containers.

---

### 6.2 Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/Fidele012/Temba_Digital_Bridge.git
cd Temba_Digital_Bridge
```

The project has two top-level folders:

```text
Temba_Digital_Bridge/
├── temba-backend/      # FastAPI Python backend
└── temba-v2/           # Frontend (HTML / CSS / JS)
```

---

### 6.3 Backend Setup

Choose **Option A (Docker — easiest)** or **Option B (manual install)**.

---

#### Option A — Docker Compose (Recommended)

This starts PostgreSQL, Redis, MinIO, the API server, the Celery worker, and Flower in a single command.

##### Step 1 — Create the environment file

```bash
cd temba-backend
cp .env.example .env
```

If `.env.example` does not exist, create `.env` manually with the content from [Section 7](#7-environment-variables) below.

##### Step 2 — Build and start all services

```bash
docker compose up -d --build
```

Wait about 30 seconds for all containers to become healthy. Check status:

```bash
docker compose ps
```

All services should show `healthy` or `running`.

##### Step 3 — Run database migrations

```bash
docker compose exec api alembic upgrade head
```

##### Step 4 — Seed initial data

```bash
docker compose exec api python seed_providers.py
```

##### Step 5 — Verify the API is running

Open your browser and go to `http://localhost:8000/docs`. You should see the Temba API Swagger documentation with all endpoints listed.

---

#### Option B — Manual (without Docker)

Use this if you prefer to install PostgreSQL and Redis directly on your machine.

##### Step 1 — Create and activate a Python virtual environment

```bash
cd temba-backend

# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

##### Step 2 — Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

##### Step 3 — Set up PostgreSQL

Open `psql` (or pgAdmin) and run:

```sql
CREATE USER temba WITH PASSWORD 'temba_pass';
CREATE DATABASE temba_db OWNER temba;
GRANT ALL PRIVILEGES ON DATABASE temba_db TO temba;
```

##### Step 4 — Set up Redis

Make sure Redis is running on the default port `6379`. On Windows use the Redis Windows installer or WSL. On macOS:

```bash
brew install redis && brew services start redis
```

##### Step 5 — Configure environment variables

```bash
cp .env.example .env
# Open .env and fill in the values from Section 7
```

##### Step 6 — Run database migrations

```bash
alembic upgrade head
```

##### Step 7 — Seed initial data

```bash
python seed_providers.py
```

This creates three approved water providers and the admin account:

| Account | Email | Password |
| --- | --- | --- |
| Admin | admin@temba.rw | Admin@Temba2025! |
| WASAC (Provider) | info@wasac.rw | Temba@Provider2025! |
| IRIBA Water Group | support@iriba.rw | Temba@Provider2025! |
| Pro Water Rwanda | hello@prowater.rw | Temba@Provider2025! |

##### Step 8 — Start the API server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

##### Step 9 — Start the Celery worker

Open a second terminal, activate the venv, then run:

```bash
celery -A app.worker worker --loglevel=info
```

---

### 6.4 Frontend Setup

The frontend is plain HTML / CSS / JavaScript — no build step required.

#### Step 1 — Open the project in VS Code

```bash
code temba-v2
```

#### Step 2 — Install the Live Server extension

In VS Code, install **Live Server** (by Ritwick Dey) from the Extensions panel.

#### Step 3 — Launch the app

Right-click `temba-v2/index.html` → **Open with Live Server**.

Your browser will open at `http://127.0.0.1:5500`.

#### Step 4 — Verify the API connection

The frontend connects to the backend at `http://127.0.0.1:8000` by default. Make sure the backend is running before logging in or submitting reports.

Available pages:

| Page | URL |
|---|---|
| Landing / Tracking | `http://127.0.0.1:5500/index.html` |
| Sign In | `http://127.0.0.1:5500/signin.html` |
| Sign Up | `http://127.0.0.1:5500/signup.html` |
| Community Dashboard | `http://127.0.0.1:5500/dashboard-community.html` |
| Submit Report | `http://127.0.0.1:5500/report.html` |
| Provider Dashboard | `http://127.0.0.1:5500/dashboard-provider.html` |

---

### 6.5 Africa's Talking USSD Setup

The USSD channel lets feature-phone users access the platform by dialling `*384*36640#`.

#### Step 1 — Create an Africa's Talking account

Go to [africastalking.com](https://africastalking.com) → Sign Up → select Sandbox (free for development).

#### Step 2 — Get your API credentials

Dashboard → Settings → API Key. Copy the key into your `.env`:

```ini
AT_USERNAME=sandbox
AT_API_KEY=your_api_key_here
AT_SENDER_ID=+250790147995
AT_USSD_CODE=*384*36640#
```

#### Step 3 — Expose your local server with ngrok

```bash
ngrok http 8000
```

Copy the HTTPS URL shown, e.g. `https://abc123.ngrok-free.app`.

#### Step 4 — Register the USSD callback

In the Africa's Talking dashboard:

- Go to **Sandbox → USSD → Create Channel**
- Set **Callback URL**: `https://abc123.ngrok-free.app/api/v1/ussd/callback`
- Save

#### Step 5 — Test the USSD flow

In the Africa's Talking dashboard:

- Go to **Sandbox → Simulator**
- Enter a test phone number (e.g. `+250700000001`)
- Dial `*384*36640#`
- Navigate the menus to register, report an issue, or check a tracking code

After submitting a report, an SMS with the tracking code is sent to your test number. Enter that code at `http://127.0.0.1:5500/index.html` to track the issue.

---

## 7. Environment Variables

Create `temba-backend/.env` with the following content. Values marked `CHANGE_ME` must be updated before running the application.

```ini
# ─── Application ───────────────────────────────────────────────
APP_NAME="Temba Digital Bridge"
APP_VERSION="1.0.0"
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=CHANGE_ME_use_a_64_character_random_string_here
ALLOWED_HOSTS=["localhost","127.0.0.1","0.0.0.0","*.ngrok.io","*.ngrok-free.app"]

# ─── Database ──────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://temba:temba_pass@localhost:5432/temba_db
DATABASE_URL_SYNC=postgresql://temba:temba_pass@localhost:5432/temba_db

# ─── Redis ─────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ─── JWT ───────────────────────────────────────────────────────
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ─── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080","http://127.0.0.1:5500","http://localhost:5500"]

# ─── Africa's Talking ─────────────────────────────────────────
AT_USERNAME=sandbox
AT_API_KEY=CHANGE_ME_your_at_api_key
AT_SENDER_ID=+250790147995
AT_USSD_CODE=*384*36640#

# ─── File Storage (MinIO) ─────────────────────────────────────
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=temba-uploads
S3_REGION=us-east-1
MAX_FILE_SIZE_MB=10

# ─── Email ─────────────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=CHANGE_ME_your_gmail_address
SMTP_PASSWORD=CHANGE_ME_your_gmail_app_password
EMAILS_FROM_NAME="Temba Digital Bridge"
EMAILS_FROM_EMAIL=CHANGE_ME_your_gmail_address

# ─── Admin seed account ───────────────────────────────────────
FIRST_ADMIN_EMAIL=admin@temba.rw
FIRST_ADMIN_PASSWORD=Admin@Temba2025!

# ─── Rate Limiting ─────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_AUTH_PER_MINUTE=10
```

> **Security note:** Never commit `.env` to Git. It is already listed in `.gitignore`.

---

## 8. Deployment Plan

Temba Digital Bridge is deployed as two separate parts: the **frontend** on Vercel and the **backend** on a persistent cloud server.

---

### 8.1 Frontend — Vercel

The `temba-v2/` folder is a static site (HTML + CSS + JS) and deploys to Vercel in minutes.

#### Step 1 — Push the project to GitHub

```bash
git add .
git commit -m "ready for deployment"
git push origin main
```

#### Step 2 — Connect to Vercel

1. Go to [vercel.com](https://vercel.com) → Log in with GitHub
2. Click **Add New → Project**
3. Select your `Temba_Digital_Bridge` repository
4. In the configuration screen set:
   - **Framework Preset**: Other
   - **Root Directory**: `temba-v2`
   - **Build Command**: *(leave empty)*
   - **Output Directory**: `.`
5. Click **Deploy**

Vercel will give you a public URL like `https://temba-digital-bridge.vercel.app`.

#### Step 3 — Update the API base URL

Before deploying, find and replace across all files in `temba-v2/`:

```text
http://127.0.0.1:8000
```

Replace with your production backend URL:

```text
https://your-backend-url.up.railway.app
```

Then commit, push, and Vercel will automatically redeploy.

#### Step 4 — Custom domain (optional)

In Vercel → Project → Domains, add a custom domain like `temba.rw`.

---

### 8.2 Backend — Railway

The FastAPI backend requires PostgreSQL, Redis, and a persistent server — Vercel's serverless functions are not suitable for this. **Railway** is the simplest cloud platform for this stack and has a free starter tier.

#### Step 1 — Sign up at Railway

Go to [railway.app](https://railway.app) and sign up with GitHub.

#### Step 2 — Create a new project

Click **New Project → Deploy from GitHub repo** → select `Temba_Digital_Bridge`. Set the **Root Directory** to `temba-backend`.

#### Step 3 — Add services

In the Railway project dashboard, click `+` and add:

- **PostgreSQL** → Database → PostgreSQL
- **Redis** → Database → Redis

Railway gives you internal connection strings for each service.

#### Step 4 — Set environment variables

In Railway → your API service → Variables, add all values from Section 7. Use Railway's reference syntax:

```text
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
DATABASE_URL_SYNC=postgresql://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
REDIS_URL=redis://${{Redis.REDIS_URL}}
CELERY_BROKER_URL=redis://${{Redis.REDIS_URL}}/1
CELERY_RESULT_BACKEND=redis://${{Redis.REDIS_URL}}/2
```

#### Step 5 — Deploy

Railway detects the `Dockerfile` in `temba-backend/` and builds automatically. The Dockerfile runs `alembic upgrade head` before starting Uvicorn, so migrations apply on every deploy.

#### Step 6 — Run the seed script once

In Railway → your service → Shell tab:

```bash
python seed_providers.py
```

#### Step 7 — Note your public backend URL

Railway gives you a URL like `https://temba-backend.up.railway.app`. Use this in the Vercel API URL update above.

---

### 8.3 USSD in Production

For production, replace the ngrok URL with your Railway backend URL in the Africa's Talking dashboard:

- **USSD Callback URL**: `https://temba-backend.up.railway.app/api/v1/ussd/callback`

Update your Railway environment variables:

```ini
AT_USERNAME=your_production_at_username
AT_API_KEY=your_production_api_key
```

---

### 8.4 Deployment Summary

| Service | Platform | URL |
| --- | --- | --- |
| Frontend | Vercel | `https://temba-digital-bridge.vercel.app` |
| Backend API | Railway | `https://temba-backend.up.railway.app` |
| API Docs (Swagger) | Railway | `https://temba-backend.up.railway.app/docs` |
| USSD Channel | Africa's Talking | `*384*36640#` |
| Database | Railway (PostgreSQL 16) | internal |
| Cache / Queue | Railway (Redis 7) | internal |

---

## 9. API Reference

The full interactive API documentation is auto-generated by FastAPI:

```text
http://localhost:8000/docs                       (local)
https://temba-backend.up.railway.app/docs        (production)
```

### Key Endpoints

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | None | Log in, receive JWT tokens |
| POST | `/api/v1/auth/refresh` | Refresh token | Get new access token |
| POST | `/api/v1/users/register` | None | Create community account |
| GET | `/api/v1/reports` | JWT | List reports (scoped by role) |
| POST | `/api/v1/reports` | JWT | Submit a new report |
| PUT | `/api/v1/reports/{id}` | JWT (provider/admin) | Update report status |
| POST | `/api/v1/reports/{id}/verify` | JWT (owner) | Verify resolution |
| GET | `/api/v1/track/{ref}` | None | Public issue tracking (no login) |
| POST | `/api/v1/ussd/callback` | AT signature | USSD callback (feature phones) |
| GET | `/api/v1/appointments` | JWT | List appointments |
| POST | `/api/v1/appointments` | JWT | Book appointment |
| GET | `/api/v1/service-requests` | JWT | List service requests |
| POST | `/api/v1/service-requests` | JWT | Submit service request |
| GET | `/api/v1/providers` | None | List approved providers |
| POST | `/api/v1/providers` | JWT | Register as provider |
| GET | `/api/v1/analytics/stats` | JWT (admin) | Platform-wide statistics |
| GET | `/api/v1/notifications` | JWT | In-app notification feed |

---

## 10. Project Structure

```text
Temba_Digital_Bridge/
│
├── temba-v2/                          # Frontend (static HTML/CSS/JS)
│   ├── index.html                     # Landing page + public tracker
│   ├── signin.html                    # Login for all user roles
│   ├── signup.html                    # Community registration
│   ├── forgot-password.html           # Password reset
│   ├── dashboard-community.html       # Community member dashboard
│   ├── dashboard-provider.html        # Water provider dashboard
│   ├── report.html                    # Submit a water issue report
│   ├── report-detail.html             # View single report timeline
│   ├── temba-chatbot.js               # In-page AI chatbot widget
│   ├── temba-about.js                 # About / info modal
│   └── rwanda_data.js                 # Rwanda administrative hierarchy data
│
├── temba-backend/                     # Backend (FastAPI / Python 3.11)
│   ├── app/
│   │   ├── main.py                    # FastAPI application entry point
│   │   ├── api/v1/
│   │   │   ├── router.py              # All routers registered here
│   │   │   └── endpoints/
│   │   │       ├── auth.py            # Login, refresh, logout
│   │   │       ├── users.py           # Profile, avatar upload
│   │   │       ├── providers.py       # Provider registration and approval
│   │   │       ├── reports.py         # Issue reporting lifecycle
│   │   │       ├── service_requests.py# Water service requests
│   │   │       ├── appointments.py    # Booking and scheduling
│   │   │       ├── notifications.py   # In-app notifications
│   │   │       ├── analytics.py       # Admin statistics
│   │   │       ├── ussd.py            # USSD callback + bilingual menus
│   │   │       └── track.py           # Public issue tracking (no auth)
│   │   ├── models/
│   │   │   ├── user.py                # User, UserRole
│   │   │   ├── provider.py            # Provider, ProviderStaff, ServiceArea
│   │   │   ├── report.py              # Report, ReportMedia
│   │   │   ├── service_request.py     # ServiceRequest
│   │   │   ├── appointment.py         # Appointment
│   │   │   └── notification.py        # Notification
│   │   ├── schemas/                   # Pydantic v2 request/response schemas
│   │   ├── core/
│   │   │   ├── config.py              # Settings loaded from .env
│   │   │   ├── security.py            # JWT creation and bcrypt helpers
│   │   │   ├── dependencies.py        # get_current_user, require_staff, etc.
│   │   │   └── sla.py                 # SLA deadline calculator per category
│   │   ├── db/
│   │   │   └── session.py             # Async SQLAlchemy session factory
│   │   ├── services/
│   │   │   ├── file_service.py        # MinIO / S3 upload handling
│   │   │   ├── notification_service.py# In-app notification helper
│   │   │   └── sms_service.py         # Africa's Talking SMS wrapper
│   │   └── worker/
│   │       └── tasks.py               # Celery SLA escalation jobs
│   ├── alembic/
│   │   └── versions/                  # Auto-generated migration files
│   ├── tests/
│   │   ├── test_auth.py
│   │   ├── test_reports.py
│   │   └── test_appointments.py
│   ├── seed_providers.py              # Seeds 3 providers + admin account
│   ├── requirements.txt               # Python dependencies
│   ├── Dockerfile                     # Multi-stage build (Python 3.11 slim)
│   ├── docker-compose.yml             # 6-service stack definition
│   ├── alembic.ini                    # Alembic configuration
│   └── .env                           # Secrets — never committed to Git
│
└── docs/                              # Documentation assets
    ├── screenshots/                   # App interface screenshots (22 screens)
    │   ├── Landing.png
    │   ├── Signin.png
    │   ├── Signup_community.png
    │   ├── Signup_water_provider.png
    │   ├── Reset_Password.png
    │   ├── Language_switching.png
    │   ├── Community_member_portal.png
    │   ├── Community_report.png
    │   ├── History.png
    │   ├── Accountability_individual.png
    │   ├── Water_quality.png
    │   ├── Service_request.png
    │   ├── Service_requested.png
    │   ├── Appointment_booking.png
    │   ├── Appointments_booked.png
    │   ├── Providers.png
    │   ├── Members_requested_services.png
    │   ├── Water_provider_portal.png
    │   ├── Reports_inbox.png
    │   ├── My_availability.png
    │   ├── Alerts_Announcements.png
    │   └── Announcements_publishing.png
    ├── figma/                         # Figma frame exports (optional)
    └── diagrams/
        └── architecture.png           # System architecture diagram
```

---

## 11. Database Schema

The backend uses **PostgreSQL 16** with **SQLAlchemy 2 (async)**. Every table shares two mixins applied at the ORM level:

| Mixin | Columns added |
|---|---|
| `UUIDMixin` | `id UUID PRIMARY KEY DEFAULT uuid4()` |
| `TimestampMixin` | `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ` |

---

### 11.1 Entity Relationship Overview

```text
users ──────────────────────────────────────────────────┐
 │ 1                                                     │
 ├──< reports          (user_id FK, CASCADE)             │
 ├──< service_requests (user_id FK, CASCADE)             │ SET NULL
 ├──< appointments     (user_id FK, CASCADE)             │ on delete
 ├──< notifications    (user_id FK, CASCADE)             │
 ├──1 providers        (user_id FK, UNIQUE)              │
 └──< provider_staff   (user_id FK) ◄────────────────────┘

providers ──────────────────────────────────────────────┐
 │ 1                                                     │
 ├──< provider_service_areas (provider_id FK, CASCADE)   │
 ├──< provider_staff         (provider_id FK, CASCADE)   │
 ├──< reports                (provider_id FK, SET NULL)  │
 ├──< service_requests       (provider_id FK, SET NULL)  │
 └──< appointments           (provider_id FK, CASCADE)   │

reports ──< report_media (report_id FK, CASCADE)

announcements → authored by users (author_id FK, SET NULL)
audit_logs    → actor is a user   (actor_id FK, SET NULL)
```

---

### 11.2 Table Definitions

#### `users`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `email` | VARCHAR(255) | UNIQUE, NOT NULL, indexed |
| `phone` | VARCHAR(20) | UNIQUE, nullable, indexed |
| `hashed_password` | VARCHAR(255) | NOT NULL |
| `full_name` | VARCHAR(255) | NOT NULL |
| `role` | ENUM | `community` / `provider` / `admin` |
| `is_active` | BOOLEAN | default `true` |
| `is_verified` | BOOLEAN | default `false` |
| `avatar_url` | TEXT | nullable |
| `province` / `district` / `sector` / `cell` / `village` | VARCHAR(100) | nullable — Rwanda location |
| `ussd_pin_hash` | VARCHAR(255) | nullable — bcrypt hashed 4-digit PIN for feature-phone access |
| `verification_token` | VARCHAR(255) | nullable |
| `reset_token` | VARCHAR(255) | nullable |
| `reset_token_expires` | TIMESTAMPTZ | nullable |
| `last_login` | TIMESTAMPTZ | nullable |

---

#### `providers`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, UNIQUE, indexed |
| `organization_name` | VARCHAR(255) | NOT NULL |
| `registration_number` | VARCHAR(100) | UNIQUE, nullable |
| `status` | ENUM | `pending` / `approved` / `suspended` / `rejected` |
| `service_categories` | VARCHAR[] | PostgreSQL ARRAY (8 standard categories) |
| `custom_services` | VARCHAR[] | PostgreSQL ARRAY |
| `description` | TEXT | nullable |
| `logo_url` | TEXT | nullable |
| `website` / `phone` / `email` | VARCHAR | nullable |
| `working_days` | VARCHAR[] | PostgreSQL ARRAY |
| `work_start_time` / `work_end_time` | VARCHAR(5) | nullable — `"HH:MM"` |
| `max_appointments_per_day` | INTEGER | default 10 |
| `unavailable_dates` | VARCHAR[] | PostgreSQL ARRAY |

---

#### `provider_service_areas`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `provider_id` | UUID | FK → `providers.id` CASCADE, indexed |
| `province` | VARCHAR(100) | NOT NULL |
| `district` | VARCHAR(100) | nullable |
| `sector` | VARCHAR(100) | nullable |

---

#### `provider_staff`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `provider_id` | UUID | FK → `providers.id` CASCADE, indexed |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `staff_role` | ENUM | `supervisor` / `regional_manager` / `executive` |

---

#### `reports`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `provider_id` | UUID | FK → `providers.id` SET NULL, nullable, indexed |
| `category` | ENUM | `contamination` / `pipe_burst` / `low_pressure` / `no_supply` / `water_quality` / `billing` / `meter` / `other` |
| `urgency` | ENUM | `low` / `medium` / `high` / `critical` |
| `status` | ENUM | `open` → `acknowledged` → `in_progress` → `resolution_submitted` → `verified` / `closed_unverified` / `management_review` |
| `title` | VARCHAR(255) | NOT NULL |
| `description` | TEXT | NOT NULL |
| `reference_number` | VARCHAR(20) | UNIQUE, nullable, indexed (e.g. `RPT-20260614-K7M3`) |
| `resolution_notes` | TEXT | nullable |
| `sla_deadline` | TIMESTAMPTZ | nullable — set on creation per category |
| `overdue_flagged` | BOOLEAN | default `false` |
| `escalation_level` | INTEGER | default 0 — 0 to 4, incremented by Celery task |
| `reopen_count` | INTEGER | default 0 |
| `first_responded_at` | TIMESTAMPTZ | nullable |
| `resolution_submitted_at` | TIMESTAMPTZ | nullable |
| `verified_at` | TIMESTAMPTZ | nullable |
| `province` / `district` / `sector` / `cell` / `village` | VARCHAR(100) | nullable |
| `latitude` / `longitude` | FLOAT | nullable |

---

#### `report_media`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `report_id` | UUID | FK → `reports.id` CASCADE, indexed |
| `url` | TEXT | NOT NULL — MinIO/S3 object URL |
| `media_type` | VARCHAR(50) | `image` / `video` / `document` |
| `file_name` | VARCHAR(255) | nullable |
| `file_size` | INTEGER | nullable (bytes) |

---

#### `service_requests`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `provider_id` | UUID | FK → `providers.id` SET NULL, nullable, indexed |
| `request_type` | ENUM | `water_connection` / `tank_delivery` / `truck_delivery` / `meter_support` / `inspection` |
| `urgency` | ENUM | `low` / `medium` / `high` |
| `status` | ENUM | `submitted` → `acknowledged` → `approved` → `in_progress` → `resolution_submitted` → `verified` / `closed_unverified` / `rejected` / `cancelled` |
| `reference_number` | VARCHAR(20) | UNIQUE, nullable, indexed |
| `description` | TEXT | NOT NULL |
| `provider_notes` | TEXT | nullable |
| `sla_deadline` | TIMESTAMPTZ | nullable |
| `overdue_flagged` | BOOLEAN | default `false` |
| `escalation_level` | INTEGER | default 0 |
| `reopen_count` | INTEGER | default 0 |
| `first_responded_at` / `resolution_submitted_at` / `verified_at` | TIMESTAMPTZ | nullable |
| `province` / `district` / `sector` / `cell` / `village` | VARCHAR(100) | nullable |
| `address_detail` | VARCHAR(500) | nullable |

---

#### `appointments`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `provider_id` | UUID | FK → `providers.id` CASCADE, indexed |
| `reason` | ENUM | `water_connection` / `meter_reading` / `pipe_repair` / `consultation` / `inspection` / `billing` / `other` |
| `meeting_type` | ENUM | `in_person` / `phone_call` / `site_visit` |
| `status` | ENUM | `pending` / `approved` / `rejected` / `reschedule_requested` / `rescheduled` / `cancelled` / `resolution_submitted` / `verified` / `closed_unverified` |
| `notes` | TEXT | nullable |
| `appointment_date` | DATE | NOT NULL — confirmed date |
| `appointment_time` | VARCHAR(5) | NOT NULL — `"HH:MM"` |
| `requested_date` / `requested_time` | DATE / VARCHAR(5) | nullable — user reschedule request |
| `reschedule_reason` | TEXT | nullable |
| `proposed_date` / `proposed_time` | DATE / VARCHAR(5) | nullable — provider counter-proposal |
| `proposed_message` | TEXT | nullable |
| `provider_note` | TEXT | nullable — rejection or cancellation reason |
| `sla_deadline` | TIMESTAMPTZ | nullable |
| `overdue_flagged` | BOOLEAN | default `false` |
| `escalation_level` | INTEGER | default 0 |
| `resolution_submitted_at` / `verified_at` | TIMESTAMPTZ | nullable |

---

#### `notifications`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `notification_type` | ENUM | `report_update` / `service_request_update` / `appointment_update` / `announcement` / `system` |
| `title` | VARCHAR(255) | NOT NULL |
| `body` | TEXT | NOT NULL |
| `is_read` | BOOLEAN | default `false` |
| `reference_id` | VARCHAR(36) | nullable — UUID of related entity |
| `reference_type` | VARCHAR(50) | nullable — `"report"` / `"appointment"` / `"service_request"` |

---

#### `announcements`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `author_id` | UUID | FK → `users.id` SET NULL, nullable |
| `title` | VARCHAR(255) | NOT NULL |
| `body` | TEXT | NOT NULL |
| `audience` | ENUM | `all` / `community` / `providers` |
| `is_pinned` | BOOLEAN | default `false` |
| `is_published` | BOOLEAN | default `true` |
| `published_at` / `expires_at` | TIMESTAMPTZ | nullable |

---

#### `audit_logs`

Rows are **never updated or deleted** — this is an immutable audit trail.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `actor_id` | UUID | FK → `users.id` SET NULL, nullable, indexed |
| `actor_role` | VARCHAR(50) | nullable |
| `action` | VARCHAR(100) | NOT NULL, indexed |
| `resource_type` | VARCHAR(100) | NOT NULL |
| `resource_id` | VARCHAR(36) | nullable |
| `ip_address` | VARCHAR(45) | nullable |
| `user_agent` | VARCHAR(500) | nullable |
| `extra` | JSONB | nullable — arbitrary metadata per action |
| `status_code` | INTEGER | nullable |

---

### 11.3 Key Design Decisions

| Decision | Reason |
|---|---|
| UUID primary keys on all tables | No sequential ID guessing; safe for distributed use |
| Rwanda location fields denormalized onto `users`, `reports`, `service_requests` | Avoids joins on the most common query patterns |
| PostgreSQL `ARRAY` for `service_categories`, `working_days`, `unavailable_dates` | Simple multi-value fields that do not warrant their own join tables |
| `sla_deadline` + `overdue_flagged` + `escalation_level` on 3 tables | Powers the hourly Celery SLA checker with 4-level escalation (officer → supervisor → regional manager → executive) |
| `reopen_count` + `first_responded_at` + `verified_at` | Inputs to the provider accountability score formula |
| `audit_logs` as append-only | Compliance requirement; tamper-evident history of every status change and user action |
| `reference_id` + `reference_type` on `notifications` | Polymorphic link to any entity type without separate FK columns per entity |
| bcrypt pinned to `3.2.2` | passlib 1.7.4 is incompatible with bcrypt ≥ 4 |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "add: your feature description"`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Open a Pull Request against `main`

---

## License

This project was built as part of the ALU Software Engineering programme.

**Author:** Fidele Ndihokubwayo
**Email:** f.ndihokubw1@alustudent.com
**GitHub:** [github.com/Fidele012](https://github.com/Fidele012)

---

*Temba Digital Bridge — Pushing communities and water providers forward, together.*
