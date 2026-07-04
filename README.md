# Temba Digital Bridge

> A bilingual (English / Kinyarwanda) civic-tech platform that connects Rwandan communities to water service providers through a responsive web interface and a USSD feature-phone channel — so every citizen, regardless of smartphone access, can report water issues, book appointments, and track resolutions in real time.

![Tests](https://img.shields.io/badge/tests-96%2F96%20passing-2E7D32?style=flat-square)
![Coverage](https://img.shields.io/badge/coverage-65%25-0097A7?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.11%2B-1565C0?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/licence-ALU%20Capstone-0A2540?style=flat-square)

---

![Temba Digital Bridge — Landing Page](docs/screenshots/Landing.png)

> **[GitHub Repository](https://github.com/Fidele012/Temba-Digital-Bridge-USSD-Web-app-platform)**

---

## Table of Contents

1. [Project Description](#1-project-description)
2. [Functional Requirements](#2-functional-requirements)
3. [Non-Functional Requirements](#3-non-functional-requirements)
4. [Key Features](#4-key-features)
5. [System Architecture](#5-system-architecture)
6. [Technology Stack](#6-technology-stack)
7. [Demo Video](#7-demo-video)
8. [Testing](#8-testing)
9. [Designs](#9-designs)
   - [Figma Prototype](#91-figma-prototype)
   - [App Interface Screenshots](#92-app-interface-screenshots)
10. [Getting Started](#10-getting-started)
    - [Prerequisites](#101-prerequisites)
    - [Clone the Repository](#102-clone-the-repository)
    - [Backend Setup](#103-backend-setup)
    - [Frontend Setup](#104-frontend-setup)
    - [Africa's Talking USSD Setup](#105-africas-talking-ussd-setup)
11. [Environment Variables](#11-environment-variables)
12. [Deployment Plan](#12-deployment-plan)
13. [API Reference](#13-api-reference)
14. [Project Structure](#14-project-structure)
15. [Database Schema](#15-database-schema)

---

## 1. Project Description

### Problem Statement

Access to clean water is a fundamental human right, yet millions of Rwandans still face daily challenges with water supply disruption, pipe bursts, contamination, and billing errors. The gap between affected communities and the water service providers responsible for resolving those issues is wide — residents have no reliable, structured way to report problems, track progress, or hold providers accountable. Meanwhile, providers lack visibility into their service quality and response times.

This problem is acute in Karangazi Sector, Mbale Cell, Nyagatare District, Rwanda's Eastern Province, where 60% of households report regular water infrastructure failures (NISR, 2025), yet complaints relied on informal escalation through local leaders with no tracking, acknowledgement, or accountability mechanism.

### What Temba Digital Bridge Does

**Temba Digital Bridge** (Kinyarwanda: *temba* — "to push forward") is a full-stack civic-tech platform that bridges this gap through four complementary components.

**Community Web Platform** — A responsive website where community members can:

- Register and set up a profile with their Rwanda administrative location (province → district → sector → cell → village)
- Submit detailed water issue reports with category, urgency level, and optional photos
- Book service appointments directly with water providers
- Track any submitted issue in real time using a unique reference code (e.g. `RPT-20260614-K7M3`)
- Receive in-app and SMS notifications at every stage of resolution
- Verify whether a provider's resolution actually fixed their problem
- Submit an anonymous star rating after verification

**USSD Feature-Phone Channel** — Accessible by dialling `*384*36640#` on any basic mobile phone, no internet required. Community members can:

- Register a Temba account entirely via feature phone, navigating Rwanda's full five-level administrative hierarchy through numbered menus
- Report water issues by selecting category and urgency from paginated menus
- Check the status of previously submitted reports
- Receive an SMS confirmation with a unique tracking code after every submission

**Provider Dashboard** — Water service organisations (WASAC, IRIBA, Pro Water Rwanda, and others) access a dedicated dashboard to:

- View all reports and service requests sorted by priority (P1 Critical → P2 Urgent → P3 Standard)
- Update report status through a defined workflow (Acknowledged → Under Review → In Progress → Resolution Submitted)
- Manage team members (Supervisors, Regional Managers, Executives) with role-based access
- View SLA deadlines and receive escalation alerts when response times are breached
- Respond to appointment bookings and propose alternative times

**Admin Panel** — Platform administrators can:

- Approve or reject provider registrations
- Publish announcements and alerts to the platform
- Monitor platform-wide analytics (total reports, resolution rates, SLA compliance)
- View a full audit trail of every action taken on the platform

### What Makes This Unique

Unlike generic complaint portals, Temba is built specifically for Rwanda's administrative geography. The USSD registration flow contains the complete Rwanda administrative hierarchy — all 5 provinces, 30 districts, ~416 sectors — presented as numbered paginated menus. A farmer in a rural cell with no smartphone can register and file a report in the same system as an urban professional using the web app.

The platform enforces a structured **accountability loop**: a report is not "closed" by the provider alone. The community member who submitted it must verify that the issue was genuinely resolved. If they dispute the resolution, the case is automatically escalated with SMS alerts at each level and SLA deadlines tracked per priority class.

Every report is automatically classified into **P1 Critical (4h SLA)**, **P2 Urgent (24h SLA)**, or **P3 Standard (72h SLA)** based on a matrix combining report category and urgency — ensuring contamination and pipe bursts always get the fastest response regardless of user-selected urgency level.

The platform is fully **bilingual** — every USSD menu, SMS notification, and in-app label is available in both English and Kinyarwanda, toggled by the user's language preference.

### Target Users

| User Type | Access Method | Primary Need |
| --- | --- | --- |
| Community Member (urban) | Web platform | File reports, book appointments, track issues |
| Community Member (rural) | USSD `*384*36640#` | File reports, receive SMS tracking codes |
| Water Provider Staff | Web dashboard | Manage reports, update status, respond to appointments |
| Platform Admin | Web admin panel | Approve providers, publish announcements, monitor health |

---

## 2. Functional Requirements

| ID | Requirement |
|----|-------------|
| FR1 | The system shall allow community members to register and authenticate via both web (email + password) and USSD (phone number + 4-digit PIN) channels. |
| FR2 | The system shall allow water service providers to register with mandatory SLA commitments (response time, resolution time) and escalation contacts (Officer and Supervisor). |
| FR3 | Provider registration shall require admin verification before activation — a verification email is sent to the platform administrator for review. |
| FR4 | The USSD interface shall support bilingual navigation in English and Kinyarwanda, selectable at session start. |
| FR5 | Community members shall be able to report water infrastructure failures by selecting category (contamination, pipe burst, no supply, low pressure, other), urgency level, and the responsible water service provider. |
| FR6 | The system shall auto-classify reports into three priority levels: P1 Critical (4-hour SLA), P2 Urgent (24-hour SLA), P3 Standard (72-hour SLA), based on category and urgency. |
| FR7 | Each report shall generate a unique reference code (RPT-YYYYMMDD-XXXX) displayed to the community member for tracking. |
| FR8 | Community members shall be able to track report status by entering the reference code on the web platform without requiring login. |
| FR9 | Water service providers shall receive real-time in-app notifications and email alerts when new reports are assigned to their organisation. |
| FR10 | The provider dashboard shall display reports sorted by priority (P1 → P2 → P3), with color-coded badges (red, amber, blue). |
| FR11 | Providers shall be able to update report status through the lifecycle: Open → Acknowledged → In Progress → Resolution Submitted. |
| FR12 | The system shall run automated SLA monitoring (Celery Beat, hourly) that triggers escalation emails to the Officer (Level 1, 0h overdue) and Supervisor (Level 2, +24h overdue). |
| FR13 | Community members shall be able to verify provider resolutions with three verdict options: Verified, Partially Resolved, or Not Resolved. |
| FR14 | After verification, community members shall be able to submit an anonymous rating (1–5 stars with optional comment). No user_id is stored on the rating record. |
| FR15 | The system shall support appointment booking (date, time, reason, provider selection) and service request submission via both web and USSD. |
| FR16 | Community members shall be able to reset passwords via email (OTP sent to inbox) or phone number (OTP sent via SMS). |
| FR17 | All user actions shall be recorded in an immutable audit log (actor, action, resource, timestamp, IP address). |

---

## 3. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR1 | The USSD interface shall function on any mobile phone (feature phone or smartphone) without internet access. |
| NFR2 | The USSD menu shall respond within 3 seconds per interaction step. |
| NFR3 | The system shall encrypt all data transmission using HTTPS/TLS between web clients and the API server. |
| NFR4 | Passwords shall be hashed using bcrypt; JWT HS256 tokens shall be used for session management (15-minute access tokens, 7-day refresh tokens stored in Redis). |
| NFR5 | The platform shall be scalable to handle increasing numbers of users across all 5 provinces of Rwanda. |
| NFR6 | The NGINX load balancer shall perform SSL/TLS termination, Layer 7 reverse proxy routing, and per-IP rate limiting (60 requests/minute general, 10 requests/minute for auth endpoints). |
| NFR7 | The system shall support English and Kinyarwanda across all USSD menus, web interfaces, and email templates. |
| NFR8 | Real-time synchronization between USSD-submitted data and the web dashboard shall maintain < 5% data discrepancy. |
| NFR9 | The system shall store data backups regularly to prevent data loss, with PostgreSQL WAL archiving enabled. |
| NFR10 | The platform shall comply with Rwanda's data protection standards; no personal data shall be exposed in API responses beyond what is necessary for the requesting user's role. |

---

## 4. Key Features

### Community

- Bilingual interface — English and Kinyarwanda on all USSD menus, SMS messages, and web UI
- Five-level Rwanda location picker (province → district → sector → cell → village) on both web and USSD
- Issue reporting with 8 categories (contamination, pipe burst, low pressure, no supply, water quality, billing, meter, other) and 4 urgency levels
- Auto-priority classification: P1 Critical (4h SLA), P2 Urgent (24h SLA), P3 Standard (72h SLA)
- Public tracking page — enter a reference code and see full status, no account needed
- Service request submission (new water connection, truck delivery, meter support, inspection)
- Appointment booking with provider availability calendar (In-Person, Phone Call, or Site Visit)
- Resolution verification — community confirms fix before case closes
- Anonymous post-verification rating (1–5 stars + optional comment)
- Delete completed, cancelled, or resolved records from history
- SMS notifications for every status change

### Provider

- Priority-sorted report inbox: P1 Critical (red) → P2 Urgent (amber) → P3 Standard (blue)
- Completion modal with provider notes before sending resolution to community for approval
- SLA countdown indicators — visual warnings before deadlines breach
- Team management — add staff with Supervisor / Regional Manager / Executive roles
- Appointment calendar management with reschedule proposal flow
- Per-notification delete and clear-all on notification drawer
- Aggregate community star rating display (★ average/5, total reviews)

### Platform

- JWT authentication with 15-minute access tokens and 7-day refresh tokens
- Bcrypt-hashed passwords (web) and bcrypt-hashed 4-digit PINs (USSD)
- Celery-powered background job queue for hourly SLA checks and 4-level escalation
- Celery Beat daily task to auto-close cases unverified after 7 days (CLOSED_UNVERIFIED)
- MinIO (S3-compatible) file storage for report media attachments
- Immutable audit trail — every status change and user action is logged
- Rate limiting on authentication endpoints (10 req/min)
- Sentry error monitoring integration
- Full English + Kinyarwanda i18n via `temba-i18n.js`

---

## 5. System Architecture

The platform follows a **seven-phase chronological user journey** from registration to verified resolution:

**Phase 1 — User Entry (Registration):**
Community members register via web (email, password, Rwanda 5-level location hierarchy) or via USSD by dialling `*384*36640#` (name, province, district, 4-digit PIN). Water service providers register with organisation details, mandatory SLA commitments, and escalation contacts (Officer + Supervisor). Provider registration triggers a verification email to the platform administrator for review before activation.

**Phase 2 — Authentication:**
Web users authenticate via JWT HS256 (bcrypt-hashed passwords, 15-minute access tokens, 7-day refresh tokens in Redis). USSD users authenticate via 4-digit PIN verified against the phone number stored in the database. All requests pass through NGINX (SSL/TLS termination, rate limiting, API gateway routing).

**Phase 3 — Community Member Actions (FastAPI :8000):**
Authenticated community members can report water issues (category, urgency, provider selection, optional photo upload), submit service requests, book appointments (In-Person / Phone Call / Site Visit), and track issues by reference code (no login required for tracking).

**Phase 4 — Auto Priority Classification:**
Every report is automatically classified into P1 Critical (4h SLA), P2 Urgent (24h SLA), or P3 Standard (72h SLA) based on a matrix combining category and urgency. P1 is always triggered by contamination (any urgency) or pipe_burst + high/critical. The SLA deadline is set from the priority class, not the category alone.

**Phase 5 — Water Service Provider Processing:**
Providers receive reports on their dashboard sorted by priority (P1 on top, red badge). The sequential workflow is: Receive Report → Acknowledge → Work on Issue (IN_PROGRESS) → Open completion modal → Submit Resolution (RESOLUTION_SUBMITTED) → Community member receives verification banner.

**Phase 6 — SLA & Accountability Engine (Celery):**
Celery Beat runs hourly SLA checks. When a deadline is missed: Level 1 (0h overdue) → Officer receives email + SMS alert; Level 2 (+24h overdue) → Supervisor receives escalation email with full report details and escalation history. Every escalation action is recorded in the immutable audit log.

**Phase 7 — Community Verification & Anonymous Feedback:**
After the provider submits a resolution, the community member sees a purple verification banner and can choose: Confirmed Fixed (status → VERIFIED), Disputed (status → FOLLOW_UP_REQUIRED, reopen_count incremented; ≥ 2 disputes → MANAGEMENT_REVIEW), or No Response after 7 days (status → CLOSED_UNVERIFIED, auto-closed by Celery daily task). After verification, the community member can submit an anonymous 1–5 star rating. The Rating record stores report_id and provider_id but intentionally omits user_id — anonymity is enforced at the data model level.

**Infrastructure:**
PostgreSQL 16 (primary database), Redis 7 (JWT token store, Celery task queue, OTP codes), MinIO S3 (report photo uploads), Africa's Talking (USSD gateway + SMS delivery), Gmail SMTP (verification, password reset OTPs, SLA escalation, provider verification emails).

```text
┌──────────────────────┐    ┌────────────────────────┐
│   Community Web App  │    │  Provider Web Dashboard │
│  (temba-v2/*.html)   │    │  (dashboard-provider   │
│   Vanilla JS / CSS   │    │   .html)                │
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
  │ Africa's Talking │────▶│  HTTPS endpoint      │
  │  USSD Gateway    │     │  → /api/v1/ussd/     │
  └──────────────────┘     │    callback          │
                           └──────────────────────┘
```

---

## 6. Technology Stack

| Layer | Technology | Version |
| --- | --- | --- |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | — |
| **Internationalisation** | Custom i18n engine (`temba-i18n.js`) | — |
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
| **Load Balancer** | NGINX 1.25 | SSL/TLS termination, rate limiting |
| **Containerisation** | Docker + Docker Compose | — |
| **USSD Tunnel (dev)** | ngrok | — |
| **Error Monitoring** | Sentry | 2.2.0 |
| **Logging** | structlog | 24.1.0 |
| **Testing** | pytest + pytest-asyncio + httpx | — |

---

## 7. Demo Video

A full technical walkthrough demonstrating the complete Temba Digital Bridge system — USSD feature-phone flow, web dashboard, chatbot, and provider management.

> **[Watch the Demo Video →](https://youtu.be/35idZ4yx3IM)**
>
> The video covers: account registration (web + USSD), submitting a water issue report, the provider dashboard SLA indicators, the AI-powered chatbot routing users to the right water provider, and the end-to-end accountability loop from report to verified resolution.

---

## 8. Testing

The full test suite runs **96 tests across 12 modules** covering 8 distinct testing strategies required by the project rubric.

```bash
cd temba-backend
pytest tests/ -v --tb=short --cov=app --cov-report=term-missing
```

### Results: 96/96 passed — ~65% coverage

| Suite | Tests | Focus |
| --- | --- | --- |
| `test_unit.py` | 18 | Pure unit tests — `classify_priority`, `sla_deadline_for`, bcrypt, JWT |
| `test_system.py` | 5 | End-to-end journeys: register → report → track → verify |
| `test_functional.py` | 9 | FR-labelled tests for FR1, FR5–FR8, FR11, FR15, FR16 |
| `test_regression.py` | 7 | Regression suite — each major feature addition re-verified |
| `test_performance.py` | 5 | Response time benchmarks, concurrent users, bulk inserts |
| `test_auth.py` | 6 | Registration, login, JWT, password change |
| `test_reports.py` | 3 | Report creation, data isolation, access control |
| `test_appointments.py` | 2 | Book → approve flow, reschedule |
| `test_service_requests.py` | 3 | Create, list own, provider status update |
| `test_security.py` | 11 | JWT boundary, RBAC, input validation, SQL injection |
| `test_edge_cases.py` | 20 | Boundary values, large data, special chars, empty fields |
| `test_ussd.py` | 18 | Full bilingual USSD flows via AT callback simulation |

### Testing Strategies

**1. Unit Testing (18 tests — `test_unit.py`):** Pure function tests with no database or network. Covers `classify_priority` matrix (contamination always P1, pipe_burst+critical→P1, etc.), `sla_deadline_for` with exact hour calculations (P1=4h, P2=24h, P3=72h), bcrypt salt uniqueness (two hashes of the same password always differ), naive datetime timezone handling, and JWT token creation + expiry.

**2. Integration Testing (14 tests):** Full HTTP request → response through FastAPI, testing real endpoint behaviour with database interactions. Covers user registration (success + duplicate email rejection), login (success + wrong password), JWT token issuance, report creation with auto-generated reference numbers, appointment booking with provider approval flow, and two-way reschedule negotiation.

**3. System Testing (5 tests — `test_system.py`):** Complete end-to-end user journeys from registration to resolution. `test_full_community_report_journey` exercises register → login → submit report → verify reference code (RPT- prefix) → public track without token. `test_full_appointment_journey` books with `site_visit` meeting type → provider approves → community sees "approved".

**4. Functional Testing (9 tests — `test_functional.py`):** Tests labelled by Functional Requirement ID. FR7 verifies reference number format (RPT-YYYYMMDD-XXXX). FR15 confirms all three meeting types preserved. FR16 changes password and logs in with the new credentials to verify.

**5. Regression Testing (7 tests — `test_regression.py`):** After each major feature was added (priority classification, ratings, USSD expansion, meeting_type fix, ProviderStaff), this suite re-runs a baseline to confirm no existing behaviour was broken.

**6. Security Testing (11 tests — `test_security.py`):** Unauthenticated access returns 401. Invalid/expired JWT tokens rejected. Community members cannot access provider-only endpoints (403). Report owner isolation (user A cannot read user B's report). SQL injection attempts in email field rejected. Password hashes never exposed in API responses.

**7. Performance Testing (5 tests — `test_performance.py`):** Health check responds in under 200ms. Login responds in under 500ms. 10 concurrent report submissions complete without errors. Bulk insert of 50 reports completes in under 30 seconds. Report listing after bulk insert responds in under 1 second.

**8. Different Data Values (20 tests — `test_edge_cases.py`):**
- **Normal values:** Valid categories, urgency levels, Rwandan phone numbers, Kinyarwanda names
- **Boundary values:** Title at exact 255-char maximum accepted; 256 chars rejected (422)
- **Invalid values:** Invalid latitude (999.0) rejected; invalid email format rejected; weak password rejected
- **Empty values:** Empty full name rejected; report missing required fields rejected; service request description below minimum rejected
- **Large values:** 5,000-character description accepted without 500 error
- **Special characters:** `pH < 6.5 & turbidity > 10 NTU. Contact: info@wasac.rw #urgent` stored as-is
- **SQL injection:** `'; DROP TABLE users; --` in email field rejected at input validation layer

### Dashboard Synchronisation Testing

An end-to-end synchronisation test confirmed real-time bidirectional communication between dashboards:

1. Community member submits report → Provider sees it instantly on their dashboard
2. Provider acknowledges → Community sees "acknowledged" status immediately
3. Provider sets IN_PROGRESS → Both dashboards and public tracking reflect the change
4. Provider submits resolution with notes → Community sees status + resolution notes + verification banner
5. Community verifies → Status changes to VERIFIED across all views
6. Service request lifecycle: submitted → acknowledged (bidirectional sync verified)
7. Appointment lifecycle: pending → approved (bidirectional sync verified)

All 7 synchronisation tests passed.

### Infrastructure Notes

The test infrastructure uses three adaptations to run PostgreSQL-designed models in SQLite:

1. PostgreSQL `ARRAY` and `JSONB` column types are replaced with `TEXT` at DDL time via a SQLAlchemy `before_create` event listener.
2. A `FakeRedis` class (in-memory dict-backed) replaces all Redis operations by injecting into `app.db.redis._redis` before any endpoint code calls `get_redis()`.
3. Python-side `default=lambda: datetime.now(timezone.utc)` was added to `TimestampMixin` columns to ensure ORM objects have timestamps without relying on PostgreSQL's `RETURNING` clause.

---

## 9. Designs

### 9.1 Figma Prototype

The complete UI design for all 25 screens was created in Figma as a single-page interactive prototype. The design follows a consistent style guide:

- **Primary colour**: `#1E6B45` (Temba Green)
- **Accent colour**: `#F5A623` (Temba Amber)
- **Typography**: Inter (headings) + Source Sans Pro (body)
- **Corner radius**: 8px for cards, 4px for inputs
- **Spacing grid**: 8px base unit

[View the interactive Figma prototype →](https://www.figma.com/proto/6MxzM5aUBE9u9apc2xAzdU/Temba-Digital-Bridge-%E2%80%94-Figma-Design?node-id=5-879&t=5w10wxNi0gQWENDH-1)

#### Screen Map — All 22 Screens

**Row 1 — Authentication & Onboarding (6 screens)**

| Screen | Description |
| --- | --- |
| Landing Page | Hero section, public issue tracker, features overview |
| Sign In | Email and password login for all roles |
| Sign Up — Community | Community member registration with location picker |
| Sign Up — Provider | Water organisation registration form |
| Reset Password | Email-based password reset flow |
| Language Switching | EN ↔ Kinyarwanda language toggle UI |

**Row 2 — Community Portal (10 screens)**

| Screen | Description |
| --- | --- |
| Community Dashboard | Overview cards, quick actions, notification feed |
| Submit Report | Report category, urgency, description, photo upload |
| Report History | Full list of submitted reports with status badges |
| Individual Accountability | Single report timeline, provider updates, verify button |
| Water Quality Report | Dedicated water quality issue submission |
| Service Request | New service request form (connection, truck, meter) |
| Service Requested | Confirmation screen after service request submitted |
| Book Appointment | Provider picker, calendar, available time slots |
| Booked Appointments | List of upcoming and past appointments |
| Browse Providers | Directory of approved water service providers |

**Row 3 — Provider Portal (4 screens)**

| Screen | Description |
| --- | --- |
| Provider Dashboard | Stats cards, recent activity, SLA indicators |
| Reports Inbox | Paginated report list with filters and status controls |
| Member Services | Service requests submitted by community members |
| Availability Management | Set working days, hours, and blackout dates |

**Row 4 — Admin & Shared (2 screens)**

| Screen | Description |
| --- | --- |
| Alerts & Announcements | View platform-wide alerts and notices |
| Publish Announcement | Admin/provider announcement publishing form |

---

### 9.2 App Interface Screenshots

All screenshots below are taken from the live running application.

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

## 10. Getting Started

### 10.1 Prerequisites

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

### 10.2 Clone the Repository

```bash
git clone https://github.com/Fidele012/Temba-Digital-Bridge-USSD-Web-app-platform.git
cd Temba-Digital-Bridge-USSD-Web-app-platform
```

The project has two top-level folders:

```text
Temba-Digital-Bridge-USSD-Web-app-platform/
├── temba-backend/      # FastAPI Python backend
└── temba-v2/           # Frontend (HTML / CSS / JS)
```

---

### 10.3 Backend Setup

Choose **Option A (Docker — easiest)** or **Option B (manual install)**.

#### Option A — Docker Compose (Recommended)

This starts PostgreSQL, Redis, MinIO, the API server, the Celery worker, and Flower in a single command.

##### Step 1 — Create the environment file

```bash
cd temba-backend
cp .env.example .env
```

If `.env.example` does not exist, create `.env` manually with the content from [Section 11](#11-environment-variables) below.

##### Step 2 — Build and start all services

```bash
docker compose up -d --build
```

Wait about 30 seconds for all containers to become healthy. Check status:

```bash
docker compose ps
```

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

Make sure Redis is running on the default port `6379`. On macOS:

```bash
brew install redis && brew services start redis
```

##### Step 5 — Configure environment variables

```bash
cp .env.example .env
# Open .env and fill in the values from Section 11
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

### 10.4 Frontend Setup

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

### 10.5 Africa's Talking USSD Setup

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

## 11. Environment Variables

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

## 12. Deployment Plan

Temba Digital Bridge is deployed as two separate parts: the **frontend** on Vercel and the **backend** on Render.

---

### 12.1 Frontend — Vercel

The `temba-v2/` folder is a static site (HTML + CSS + JS) deployed to Vercel.

#### Step 1 — Push the project to GitHub

```bash
git add .
git commit -m "ready for deployment"
git push origin main
```

#### Step 2 — Connect to Vercel

1. Go to [vercel.com](https://vercel.com) → Log in with GitHub
2. Click **Add New → Project**
3. Select your `Temba-Digital-Bridge-USSD-Web-app-platform` repository
4. In the configuration screen set:
   - **Framework Preset**: Other
   - **Root Directory**: `temba-v2`
   - **Build Command**: *(leave empty)*
   - **Output Directory**: `.`
5. Click **Deploy**

The live frontend URL is: **`https://temba-digital-bridge-ussd-web-app-p.vercel.app`**

---

### 12.2 Backend — Render

The backend is deployed via a Render Blueprint (`render.yaml` at the repo root), which provisions the API, PostgreSQL database, and Redis in one step.

#### Step 1 — Sign up at Render

Go to [render.com](https://render.com) and sign up with GitHub.

#### Step 2 — Deploy the Blueprint

1. Click **New → Blueprint**
2. Connect your `Temba-Digital-Bridge-USSD-Web-app-platform` repository
3. Render detects `render.yaml` at the repo root automatically
4. Fill in the secret environment variables when prompted:
   - `AT_API_KEY` — your Africa's Talking sandbox API key
   - `SMTP_USER` — Gmail address for transactional emails
   - `SMTP_PASSWORD` — Gmail App Password (16-character code from Google Account → Security → App Passwords)
   - `EMAILS_FROM_EMAIL` — same Gmail address
   - `FIRST_ADMIN_PASSWORD` — initial password for `admin@temba.rw`
5. Click **Apply**

Render creates: the `temba-api` web service, `temba-db` PostgreSQL database, and `temba-redis` Redis instance. On first deploy, `alembic upgrade head` runs automatically before Uvicorn starts.

#### Step 3 — Run the seed script once (if providers are missing)

In Render → `temba-api` service → **Shell** tab:

```bash
python seed_providers.py
```

---

### 12.3 USSD in Production

Register the live backend URL in the Africa's Talking dashboard under your USSD service callback:

- **USSD Callback URL**: `https://temba-api.onrender.com/api/v1/ussd/callback`

---

### 12.4 Deployment Summary

| Service | Platform | URL |
| --- | --- | --- |
| Frontend | Vercel | `https://temba-digital-bridge-ussd-web-app-p.vercel.app` |
| Backend API | Render | `https://temba-api.onrender.com` |
| API Docs (Swagger) | Render | `https://temba-api.onrender.com/docs` |
| USSD Channel | Africa's Talking | `*384*36640#` |
| Database | Render (PostgreSQL 16) | internal |
| Cache / Queue | Render (Redis 7) | internal |

---

## 13. API Reference

The full interactive API documentation is auto-generated by FastAPI:

```text
http://localhost:8000/docs                   (local)
https://temba-api.onrender.com/docs          (production)
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
| POST | `/api/v1/reports/{id}/rate` | JWT (owner) | Submit anonymous rating (1–5 stars) |
| GET | `/api/v1/track/{ref}` | None | Public issue tracking (no login) |
| POST | `/api/v1/ussd/callback` | AT signature | USSD callback (feature phones) |
| GET | `/api/v1/appointments` | JWT | List appointments |
| POST | `/api/v1/appointments` | JWT | Book appointment |
| DELETE | `/api/v1/appointments/{id}` | JWT | Cancel appointment |
| GET | `/api/v1/service-requests` | JWT | List service requests |
| POST | `/api/v1/service-requests` | JWT | Submit service request |
| DELETE | `/api/v1/service-requests/{id}` | JWT | Cancel service request |
| GET | `/api/v1/providers` | None | List approved providers |
| POST | `/api/v1/providers` | JWT | Register as provider |
| GET | `/api/v1/providers/{id}/ratings` | None | Provider aggregate rating |
| GET | `/api/v1/analytics/stats` | JWT (admin) | Platform-wide statistics |
| GET | `/api/v1/notifications` | JWT | In-app notification feed |

---

## 14. Project Structure

```text
Temba-Digital-Bridge-USSD-Web-app-platform/
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
│   ├── temba.css                      # Global stylesheet
│   ├── temba-auth.js                  # Authentication helpers (JWT refresh)
│   ├── temba-chatbot.js               # In-page AI chatbot widget
│   ├── temba-about.js                 # About / info modal
│   ├── temba-i18n.js                  # Full EN + Kinyarwanda translation engine
│   ├── rwanda_data.js                 # Rwanda administrative hierarchy data
│   └── vercel.json                    # Vercel deployment configuration
│
├── temba-backend/                     # Backend (FastAPI / Python 3.11)
│   ├── app/
│   │   ├── main.py                    # FastAPI application entry point
│   │   ├── events.py                  # App startup / shutdown events
│   │   ├── worker.py                  # Celery application factory
│   │   ├── tasks.py                   # Celery SLA escalation jobs
│   │   ├── api/v1/
│   │   │   ├── router.py              # All routers registered here
│   │   │   └── endpoints/
│   │   │       ├── auth.py            # Login, refresh, logout
│   │   │       ├── users.py           # Profile, avatar upload
│   │   │       ├── providers.py       # Provider registration and approval
│   │   │       ├── reports.py         # Issue reporting lifecycle + rating
│   │   │       ├── service_requests.py# Water service requests
│   │   │       ├── appointments.py    # Booking and scheduling
│   │   │       ├── notifications.py   # In-app notifications
│   │   │       ├── analytics.py       # Admin statistics
│   │   │       ├── events.py          # SSE push events
│   │   │       ├── ussd.py            # USSD callback + bilingual menus
│   │   │       └── track.py           # Public issue tracking (no auth)
│   │   ├── models/
│   │   │   ├── user.py                # User, UserRole
│   │   │   ├── provider.py            # Provider, ProviderStaff, ServiceArea
│   │   │   ├── report.py              # Report, ReportMedia
│   │   │   ├── service_request.py     # ServiceRequest
│   │   │   ├── appointment.py         # Appointment (MeetingType enum)
│   │   │   ├── notification.py        # Notification
│   │   │   ├── announcement.py        # Announcement
│   │   │   ├── audit_log.py           # AuditLog (append-only)
│   │   │   └── rating.py              # Rating (no user_id — anonymous by design)
│   │   ├── schemas/                   # Pydantic v2 request/response schemas
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── provider.py
│   │   │   ├── report.py
│   │   │   ├── service_request.py
│   │   │   ├── appointment.py
│   │   │   ├── notification.py
│   │   │   ├── rating.py
│   │   │   └── common.py
│   │   ├── core/
│   │   │   ├── config.py              # Settings loaded from .env
│   │   │   ├── security.py            # JWT creation and bcrypt helpers
│   │   │   ├── dependencies.py        # get_current_user, require_staff, etc.
│   │   │   ├── provider_utils.py      # Provider helper utilities
│   │   │   ├── logging.py             # structlog configuration
│   │   │   └── sla.py                 # Priority classification + SLA deadline calculator
│   │   ├── db/
│   │   │   ├── session.py             # Async SQLAlchemy session factory
│   │   │   ├── base.py                # Import all models for Alembic
│   │   │   ├── base_class.py          # UUIDMixin, TimestampMixin
│   │   │   ├── init_db.py             # Admin seeding on startup
│   │   │   └── redis.py               # Redis connection factory
│   │   └── services/
│   │       ├── file_service.py        # MinIO / S3 upload handling
│   │       └── notification_service.py# In-app notification helper
│   ├── alembic/
│   │   └── versions/                  # Auto-generated migration files
│   ├── tests/
│   │   ├── conftest.py                # Async test client, SQLite fixtures, FakeRedis
│   │   ├── test_auth.py               # 6 tests — auth lifecycle
│   │   ├── test_reports.py            # 3 tests — report CRUD + access control
│   │   ├── test_appointments.py       # 2 tests — booking + reschedule
│   │   ├── test_service_requests.py   # 3 tests — service request lifecycle
│   │   ├── test_security.py           # 11 tests — JWT, RBAC, SQL injection
│   │   ├── test_edge_cases.py         # 12 tests — boundary values, enums, Unicode
│   │   └── test_ussd.py               # 18 tests — full bilingual USSD flows
│   ├── seed_providers.py              # Seeds 3 providers + admin account
│   ├── requirements.txt               # Python dependencies
│   ├── Dockerfile                     # Multi-stage build (Python 3.11 slim)
│   ├── docker-compose.yml             # 6-service stack definition
│   ├── alembic.ini                    # Alembic configuration
│   └── .env                           # Secrets — never committed to Git
│
└── docs/                              # Documentation assets
    ├── screenshots/                   # App interface screenshots (22 screens)
    ├── figma/                         # Figma frame exports
    ├── mission_capstone_chapters_3_to_6.md   # Capstone chapters 3–6
    └── mission_capstone_chapters_3_to_6.html # HTML version of capstone chapters
```

---

## 15. Database Schema

The backend uses **PostgreSQL 16** with **SQLAlchemy 2 (async)**. Every table shares two mixins applied at the ORM level:

| Mixin | Columns added |
|---|---|
| `UUIDMixin` | `id UUID PRIMARY KEY DEFAULT uuid4()` |
| `TimestampMixin` | `created_at TIMESTAMPTZ`, `updated_at TIMESTAMPTZ` |

---

### 15.1 Entity Relationship Overview

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
reports ──< ratings      (report_id FK, UNIQUE — one rating per report)

announcements → authored by users (author_id FK, SET NULL)
audit_logs    → actor is a user   (actor_id FK, SET NULL)
```

---

### 15.2 Table Definitions

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
| `ussd_pin_hash` | VARCHAR(255) | nullable — bcrypt hashed 4-digit PIN |
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
| `sla_response_hours` / `sla_resolution_hours` | INTEGER | NOT NULL — mandatory SLA commitments |
| `escalation_officer_name` / `escalation_officer_email` | VARCHAR | nullable — Level 1 escalation contact |
| `escalation_supervisor_name` / `escalation_supervisor_email` | VARCHAR | nullable — Level 2 escalation contact |
| `working_days` | VARCHAR[] | PostgreSQL ARRAY |
| `work_start_time` / `work_end_time` | VARCHAR(5) | nullable — `"HH:MM"` |
| `max_appointments_per_day` | INTEGER | default 10 |
| `unavailable_dates` | VARCHAR[] | PostgreSQL ARRAY |

---

#### `reports`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `provider_id` | UUID | FK → `providers.id` SET NULL, nullable, indexed |
| `category` | ENUM | `contamination` / `pipe_burst` / `low_pressure` / `no_supply` / `water_quality` / `billing` / `meter` / `other` |
| `urgency` | ENUM | `low` / `medium` / `high` / `critical` |
| `priority_class` | ENUM | `P1` (Critical 4h) / `P2` (Urgent 24h) / `P3` (Standard 72h) |
| `status` | ENUM | `open` → `acknowledged` → `in_progress` → `resolution_submitted` → `verified` / `closed_unverified` / `management_review` |
| `title` | VARCHAR(255) | NOT NULL |
| `description` | TEXT | NOT NULL |
| `reference_number` | VARCHAR(20) | UNIQUE, nullable, indexed (e.g. `RPT-20260614-K7M3`) |
| `resolution_notes` | TEXT | nullable |
| `sla_deadline` | TIMESTAMPTZ | nullable — set on creation per priority class |
| `overdue_flagged` | BOOLEAN | default `false` |
| `escalation_level` | INTEGER | default 0 — 0 to 4, incremented by Celery |
| `reopen_count` | INTEGER | default 0 |
| `first_responded_at` / `resolution_submitted_at` / `verified_at` | TIMESTAMPTZ | nullable |
| `province` / `district` / `sector` / `cell` / `village` | VARCHAR(100) | nullable |
| `latitude` / `longitude` | FLOAT | nullable |

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
| `description` | TEXT | NOT NULL |
| `provider_notes` | TEXT | nullable |
| `sla_deadline` | TIMESTAMPTZ | nullable |
| `escalation_level` / `reopen_count` | INTEGER | default 0 |
| `first_responded_at` / `resolution_submitted_at` / `verified_at` | TIMESTAMPTZ | nullable |
| `province` / `district` / `sector` / `cell` / `village` / `address_detail` | VARCHAR | nullable |

---

#### `appointments`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `provider_id` | UUID | FK → `providers.id` CASCADE, indexed |
| `reason` | ENUM | `water_connection` / `meter_reading` / `pipe_repair` / `consultation` / `inspection` / `billing` / `other` |
| `meeting_type` | ENUM | `in_person` / `phone_call` / `site_visit` |
| `status` | ENUM | `pending` / `approved` / `rejected` / `reschedule_requested` / `rescheduled` / `cancelled` |
| `appointment_date` | DATE | NOT NULL — confirmed date |
| `appointment_time` | VARCHAR(5) | NOT NULL — `"HH:MM"` |
| `notes` / `reschedule_reason` / `proposed_message` / `provider_note` | TEXT | nullable |
| `proposed_date` / `proposed_time` | DATE / VARCHAR(5) | nullable — provider counter-proposal |
| `sla_deadline` | TIMESTAMPTZ | nullable |
| `escalation_level` | INTEGER | default 0 |

---

#### `ratings`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `report_id` | UUID | FK → `reports.id` CASCADE, UNIQUE — one rating per report |
| `provider_id` | UUID | FK → `providers.id` CASCADE, indexed |
| `score` | INTEGER | 1–5, NOT NULL |
| `comment` | TEXT | nullable — optional text feedback |

> **Note:** The `ratings` table intentionally has **no `user_id` column**. Anonymity is enforced at the data model level — the provider can only see aggregate scores (`AVG(score)`, `COUNT(id)`), never individual raters.

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

### 15.3 Key Design Decisions

| Decision | Reason |
|---|---|
| UUID primary keys on all tables | No sequential ID guessing; safe for distributed use |
| Rwanda location fields denormalised onto `users`, `reports`, `service_requests` | Avoids joins on the most common query patterns |
| PostgreSQL `ARRAY` for `service_categories`, `working_days`, `unavailable_dates` | Simple multi-value fields that do not warrant their own join tables |
| `priority_class` + `sla_deadline` + `overdue_flagged` + `escalation_level` on 3 tables | Powers the hourly Celery SLA checker with 4-level escalation (officer → supervisor → regional manager → executive) |
| `reopen_count` + `first_responded_at` + `verified_at` | Inputs to the provider accountability score formula |
| `audit_logs` as append-only | Compliance requirement; tamper-evident history of every status change and user action |
| No `user_id` on `ratings` | Anonymity enforced at schema level — not just application level |
| `meeting_type` ENUM on `appointments` | Correctly records In-Person / Phone Call / Site Visit; prevents all meetings defaulting to in-person |
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
