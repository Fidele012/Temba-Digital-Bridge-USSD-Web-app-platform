# CHAPTER THREE: SYSTEM ANALYSIS AND DESIGN

## 3.1 Introduction

This chapter presents the system analysis, design methodology, and technical architecture of the Temba Digital Bridge platform. The system was designed following the Agile Development Model with iterative sprints, guided by Design Science Research Methodology (DSRM) principles for building and evaluating practical digital artefacts intended to address real-world governance problems. The chapter details the research design, functional and non-functional requirements, system architecture, UML diagrams, database schema, and the development tools and technologies selected for implementation.

## 3.2 Research Design

This study employs a mixed-methods research design combining quantitative system performance metrics with qualitative user feedback. The Agile Development Model governs the platform construction phase, structured into iterative two-week sprints that allow findings from community co-design sessions and usability testing to be incorporated before pilot launch. The Design Science Research Methodology (DSRM) cycle guides the overall research process: problem identification and motivation (Chapters 1 and 2), objective and solution design (this chapter), artefact development (USSD and web platform), demonstration (pilot deployment), evaluation (metrics collection and analysis), and communication (final report).

The quantitative component measures system performance through USSD task completion rates, report submission rates, issue resolution times, real-time synchronization accuracy between channels, and System Usability Scale (SUS) scores. The qualitative component captures the lived experiences, perceptions, and barriers to adoption of community members and service providers through semi-structured interviews and open-text survey responses.

### 3.2.1 Population and Sample

The target population comprises community members and water service providers in the Eastern Province of Rwanda, specifically in Karangazi Sector, Mbale Cell, Nyagatare District. The sample includes 200 households surveyed through the structured Google Forms questionnaire, 50 individuals who participated in semi-structured interviews, and over 10 community leaders consulted on water access governance and reporting barriers.

### 3.2.2 Sampling Strategy

The study employed both systematic and purposive sampling techniques. The sample size of 200 households was determined using the Yamane (1967) formula: n = N / (1 + N(e)²), where N is the total household population in Mbale Cell and e is the margin of error set at 0.05 (95% confidence level). Purposive sampling is justified because the research requires participants with direct, lived experience of the specific water access and reporting challenges the platform addresses.

### 3.2.3 Data Collection Methods

**Primary Data Collection:** A structured Google Forms survey designed in both English and Kinyarwanda was administered across households in Karangazi Sector. The survey captured evidence on water and sanitation access challenges, frequency and severity of infrastructure failures, current reporting behaviours, mobile phone type and usage patterns, USSD familiarity, and willingness to adopt a digital reporting platform. Fifty qualitative interviews with community members and over 10 community leader consultations supplemented the survey.

**Secondary Data Collection:** Systematic review of peer-reviewed academic literature, analysis of Rwanda Ministry of Infrastructure WASH MIS reports, NISR household survey data, and UNICEF Rwanda water sector situation analyses.

### 3.2.4 Data Collection Tools

- **Google Forms Survey Instrument:** A structured bilingual questionnaire with closed and open-ended questions, including Likert-scale items for readiness and attitude assessment.
- **Interview Guide:** Semi-structured questions tailored to community members and community leaders, exploring water access experiences, reporting barriers, trust in institutions, and digital readiness.
- **Field Observation Guide:** A checklist capturing system usage patterns during pilot sessions, including USSD navigation completion, session duration, error occurrences, and environmental barriers.
- **System Usability Scale (SUS):** A standardized 10-item usability questionnaire administered to all pilot users post-deployment.

### 3.2.5 Evaluation Plan

During the pilot phase, the following targets were defined:

| Metric | Target |
|--------|--------|
| SUS Score | ≥ 70 (good usability) |
| USSD task completion rate | ≥ 90% without assistance |
| Time-on-task (USSD report submission) | < 2 minutes |
| Data transmission error rate | < 5% |
| USSD-web synchronization accuracy | < 5% data discrepancy |

## 3.3 Functional and Non-Functional Requirements

### 3.3.1 Functional Requirements

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

### 3.3.2 Non-Functional Requirements

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

## 3.4 System Architecture

The Temba Digital Bridge platform follows a seven-phase chronological user journey architecture, designed for clarity and sequential understanding of how each component interacts:

**Phase 1 — User Entry (Registration):**
Community members register via the web application (email, password, Rwanda 5-level location hierarchy: Province → District → Sector → Cell → Village) or via USSD by dialing *384*36640# (name, province, district, 4-digit PIN). Water service providers register with organisation details, mandatory SLA commitments, and escalation contacts (Officer + Supervisor). Provider registration triggers a verification email to the platform administrator (tembadigitalbridge@gmail.com) for review before activation.

**Phase 2 — Authentication:**
Web users authenticate via JWT HS256 (bcrypt-hashed passwords, 15-minute access tokens, 7-day refresh tokens in Redis). USSD users authenticate via 4-digit PIN verified against the phone number stored in the database. All requests pass through NGINX (SSL/TLS termination, rate limiting, API gateway routing).

**Phase 3 — Community Member Actions (FastAPI :8000):**
Authenticated community members can report water issues (category, urgency, provider selection, optional photo upload), submit service requests (new connection, tank delivery, meter support, inspection), book appointments (provider, reason, date, time), and track issues by reference code (no login required for tracking).

**Phase 4 — Auto Priority Classification:**
Every report is automatically classified into P1 Critical (4h SLA), P2 Urgent (24h SLA), or P3 Standard (72h SLA) based on a matrix combining category and urgency. The SLA deadline is calculated from the priority class, not from the category alone.

**Phase 5 — Water Service Provider Processing:**
Providers receive reports on their dashboard, sorted by priority (P1 on top). The sequential workflow is: Receive Report → Acknowledge (first_responded_at recorded) → Work on Issue (status: IN_PROGRESS) → Submit Resolution (resolution notes + status: RESOLUTION_SUBMITTED).

**Phase 6 — SLA & Accountability Engine (Celery):**
Celery Beat runs hourly SLA checks. When a deadline is missed: Level 1 (0h overdue) → Officer receives email + SMS alert. Level 2 (+24h overdue) → Supervisor receives escalation email with full report details, community member contact information, and escalation history. Every escalation action is recorded in the immutable audit log.

**Phase 7 — Community Verification & Anonymous Feedback:**
After the provider submits a resolution, the community member is notified and can verify: Confirmed Fixed (status: VERIFIED), Disputed (status: FOLLOW_UP_REQUIRED, reopen count incremented), or No Response after 7 days (status: CLOSED_UNVERIFIED, auto-closed by Celery daily task). After verification, the community member can submit an anonymous 1–5 star rating with optional comment. The Rating record stores report_id and provider_id but intentionally omits user_id — ensuring the provider sees only aggregate scores, never individual ratings.

**Data & External Services:**
PostgreSQL 16 (primary database: users, reports, providers, ratings, audit logs), Redis 7 (JWT token store, Celery task queue, OTP codes), MinIO S3 (report photo uploads), Africa's Talking (USSD gateway + SMS delivery), Gmail SMTP (email verification, password reset OTPs, SLA escalation emails, provider verification emails).

*[System Architecture Diagram: See Figure 3.1 — docs/diagrams/system-architecture.puml]*

## 3.5 UML Diagrams

### 3.5.1 Use Case Diagram

The Use Case Diagram identifies three primary actors (Community Member via Web, Feature Phone User via USSD, Provider Staff) and one external system actor (Africa's Talking). Use cases are grouped into five packages: Authentication (Register, Login, Forgot Password, Verify Email), Community Actions (Submit Report, Track Report, Verify Resolution, Book Appointment, Submit Service Request, Browse Providers, Switch Language), USSD Channel (Register via USSD, Report Issue via USSD, Track Status via USSD), Provider Actions (Manage Reports, Update Status, Submit Resolution, Manage Appointments, Set Availability, Manage Team, View SLA Dashboard), and System Services (Send SMS Notification, Send Email, Check SLA & Escalate). Include relationships connect Register → Send Email, Report Issue → Send SMS, and Update Status → Send SMS. Extend relationships connect Book Appointment → Request Reschedule and Report Issue → Report via USSD.

*[Use Case Diagram: See Figure 3.2 — docs/diagrams/use-case.puml]*

### 3.5.2 Class Diagram

The Class Diagram models the domain using inheritance and composition. User is an abstract base class providing shared account fields (userId, email, phone, fullName, isVerified, location, passwordHash) and methods (register, login, verifyEmail, updateProfile, resetPassword). CommunityMember and WaterServiceProvider both extend User. WaterServiceProvider adds organisation-specific attributes (organizationName, registrationNumber, status, serviceCategories, slaResponseHours, slaResolutionHours) and methods (registerProvider, approve, reject, setAvailability). Report, ServiceRequest, and Appointment all inherit shared SLA-tracking behaviour (status, escalationLevel, submit, approve, reject, cancel, escalate) from an abstract Trackable class. Location is a reusable value object representing Rwanda's 5-level administrative hierarchy (province, district, sector, cell, village). Supporting entities include ProviderStaff, ProviderServiceArea, ReportMedia, Notification, Announcement, AuditLog, and Rating (with NO user_id — anonymous by design).

*[Class Diagram: See Figure 3.3 — docs/diagrams/class-diagram.puml]*

### 3.5.3 Entity Relationship Diagram (ERD)

The ERD shows 8 core physical entities (USERS, PROVIDERS, REPORTS, SERVICE_REQUESTS, APPOINTMENTS, NOTIFICATIONS, ANNOUNCEMENTS, AUDIT_LOGS) plus the USSD_SESSION virtual entity representing the stateless USSD channel. All primary keys are UUID. Solid lines represent physical foreign-key relationships; dashed lines represent USSD channel interactions (non-identifying). Key relationships: USERS ||--o| PROVIDERS ("has profile"), USERS ||--o{ REPORTS ("submits"), PROVIDERS ||--o{ REPORTS ("assigned to"), USERS ||--o{ APPOINTMENTS ("books"), PROVIDERS ||--o{ APPOINTMENTS ("attends"), USERS ||..o{ USSD_SESSION ("authenticates via PIN"), USSD_SESSION ||..o{ REPORTS ("can create").

*[ERD Diagram: See Figure 3.4 — docs/diagrams/erd.puml]*

### 3.5.4 Flowchart — Report Lifecycle & Accountability Loop

The flowchart traces the complete lifecycle of a community-submitted water issue report: Community Member submits report → System generates reference number (RPT-YYYYMMDD-XXXX) → Auto-calculates SLA deadline based on priority class → Notifies provider (in-app + SMS). If provider acknowledges within SLA: status → ACKNOWLEDGED → IN_PROGRESS → Provider submits resolution → Community member notified → Verification decision. If SLA breached: Celery hourly checker triggers escalation → Level 1 Officer email (0h) → Level 2 Supervisor email (+24h). Community verification: Confirmed Fixed → VERIFIED (case closed, anonymous rating prompted) | Disputed → FOLLOW_UP_REQUIRED (reopen_count++, if ≥2 → MANAGEMENT_REVIEW) | No Response (7 days) → CLOSED_UNVERIFIED (auto-closed). All terminal states → Audit Log (immutable record).

*[Flowchart: See Figure 3.5 — docs/diagrams/flowchart.puml]*

## 3.6 Development Tools and Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Backend Framework | FastAPI (Python 3.11) | Async REST API with OpenAPI documentation |
| Database | PostgreSQL 16 | Primary relational database with UUID PKs, JSONB, ARRAY columns |
| ORM | SQLAlchemy 2 (async) | Object-relational mapping with Alembic migrations |
| Cache & Queue | Redis 7 | JWT token storage, Celery task broker, OTP code storage |
| Task Scheduler | Celery + Celery Beat | Background SLA checking (hourly), auto-close (daily), email tasks |
| Object Storage | MinIO S3 | Report photo uploads, S3-compatible API |
| Load Balancer | NGINX 1.25 | Layer 7 reverse proxy, SSL/TLS termination, rate limiting |
| USSD Gateway | Africa's Talking API | USSD callback handling, SMS delivery |
| Email | Gmail SMTP (TLS) | Transactional emails: verification, password reset, SLA escalation |
| Authentication | JWT HS256 + bcrypt 3.2.2 | 15-min access tokens, 7-day refresh tokens, password hashing |
| Frontend | HTML5 + CSS3 + Vanilla JS | Bilingual landing page, community dashboard, provider dashboard |
| Internationalization | Custom i18n (temba-i18n.js) | Full English + Kinyarwanda translation across all interfaces |
| Error Monitoring | Sentry | Production error tracking and alerting |
| Containerization | Docker + Docker Compose | Multi-service orchestration (API, PostgreSQL, Redis, MinIO, NGINX, Celery, Flower) |
| Version Control | Git + GitHub | Source code management |
| IDE | VS Code | Development environment |
| Testing | pytest + pytest-asyncio + httpx | Async integration testing with in-memory SQLite + FakeRedis |
| Diagram Tools | PlantUML | UML diagrams (Use Case, Class, ERD, Architecture, Flowchart) |


---

# CHAPTER FOUR: SYSTEM IMPLEMENTATION AND TESTING

## 4.1 Implementation and Coding

### 4.1.1 Introduction

This chapter documents the implementation of the Temba Digital Bridge platform, detailing the technical decisions made during development, the key system components built, and the comprehensive testing strategy employed to verify correctness, security, and usability. The platform was developed using an Agile methodology with iterative two-week sprints, enabling continuous integration of community feedback into the design.

### 4.1.2 Description of Implementation

**Backend Architecture:**
The backend is built on FastAPI (Python 3.11) with SQLAlchemy 2 async ORM connecting to PostgreSQL 16. The API follows RESTful conventions with versioned endpoints under `/api/v1/`. Key architectural decisions include:

- **Shared mixins:** `UUIDMixin` (UUID primary keys via `uuid4()`) and `TimestampMixin` (auto-populated `created_at` and `updated_at` with Python-side lambda defaults for cross-database compatibility).
- **Enum handling:** All status, category, and urgency enums use `str, enum.Enum` for JSON serialization compatibility. PostgreSQL native enum types are used for type safety.
- **Session lifecycle:** FastAPI dependency injection via `get_db()` yields an async session, commits on success, and rolls back on exception — ensuring transactional consistency across all endpoints.

**USSD Implementation:**
The USSD handler (`/api/v1/ussd/callback`) is a single stateless endpoint that receives Africa's Talking POST callbacks with `sessionId`, `serviceCode`, `phoneNumber`, and `text` parameters. The entire navigation state is encoded in the `text` parameter as a `*`-separated string (e.g., `1*2*1234*1*1*1*1*1` represents: English → Login → PIN → Report → Category → Urgency → Provider → Confirm). This stateless design means no server-side session storage is required — Africa's Talking manages session state. The handler includes:

- Full Rwanda administrative hierarchy (5 provinces, 30 districts, 416 sectors, with paginated USSD menus for sector/cell/village selection)
- Bilingual prompts (English and Kinyarwanda) for all 6 main menu options
- Phone number variant matching (handles +250, 250, and 0-prefix formats)
- PIN-based authentication (bcrypt-hashed, stored as `ussd_pin_hash` on the User model)

**SLA & Accountability Engine:**
The Celery worker runs two periodic tasks:
1. `check_sla_deadlines` (hourly): Scans all open reports, service requests, and appointments with SLA deadlines in the past. For each overdue item, it checks the current escalation level and triggers the next level if the threshold is met. Level 1 (Officer) is emailed immediately at 0h overdue; Level 2 (Supervisor) is emailed at +24h with full escalation history.
2. `auto_close_unverified` (daily): Closes cases where the provider submitted a resolution but the community member did not respond within 7 days. Status is set to CLOSED_UNVERIFIED with no verification credit.

**Anonymous Rating System:**
The `Rating` model intentionally has no `user_id` foreign key. When a community member calls `POST /reports/{id}/rate`, the endpoint verifies ownership (the caller must be the report's original submitter) and that the report status is VERIFIED, but the resulting Rating record stores only `report_id`, `provider_id`, `score` (1–5), and `comment`. The provider's aggregate rating is computed on demand via `GET /providers/{id}/ratings` using SQL `AVG(score)` and `COUNT(id)`.

### 4.1.3 Key Screenshots

- **Figure 4.1:** Landing page with WASH imagery, bilingual navigation, and "Track Your Issue" form
- **Figure 4.2:** Community member registration (web) with Province → District location selection
- **Figure 4.3:** USSD welcome screen showing language selection (English / Kinyarwanda)
- **Figure 4.4:** USSD main menu with 6 service options (Report, Track, Book, Appointments, Service Requests, Submit Request)
- **Figure 4.5:** USSD report submission confirmation showing tracking code (RPT-YYYYMMDD-XXXX)
- **Figure 4.6:** Provider dashboard with priority-sorted reports (P1 Critical red, P2 Urgent amber, P3 Standard blue)
- **Figure 4.7:** Provider registration form with SLA commitment fields and escalation contacts (Officer + Supervisor)
- **Figure 4.8:** Community verification screen with three verdict options (Verified, Partially Resolved, Not Resolved)
- **Figure 4.9:** Anonymous rating modal (1–5 stars + optional comment)
- **Figure 4.10:** Public issue tracking result showing report details, status, and provider information

## 4.2 Testing

### 4.2.1 Introduction

A comprehensive multi-strategy testing approach was employed to ensure the reliability, security, and usability of the Temba Digital Bridge platform. Testing was conducted using pytest with pytest-asyncio for async endpoint testing, an in-memory SQLite database with FakeRedis for isolated test execution, and httpx AsyncClient for HTTP-level integration testing.

### 4.2.2 Testing Infrastructure

The test infrastructure required three adaptations to enable PostgreSQL-designed models to run in SQLite:
1. PostgreSQL ARRAY and JSONB column types are dynamically replaced with TEXT at DDL time via a SQLAlchemy `before_create` event listener.
2. A FakeRedis class (in-memory dict-backed) replaces all Redis operations (token storage, OTP codes, task queue) by injecting into `app.db.redis._redis` before any endpoint code calls `get_redis()`.
3. Python-side `default=lambda: datetime.now(timezone.utc)` was added to `TimestampMixin` columns to ensure ORM objects have timestamp values without relying on PostgreSQL's `RETURNING` clause.

### 4.2.3 Test Results Summary

**43 tests across 7 test files — all passed.**

| Test File | Strategy | Tests | Status |
|-----------|----------|-------|--------|
| test_auth.py | Integration Testing — Authentication lifecycle | 6 | All passed |
| test_reports.py | Integration Testing — Report CRUD & access control | 3 | All passed |
| test_appointments.py | Integration Testing — Appointment booking & reschedule | 2 | All passed |
| test_service_requests.py | Integration Testing — Service request lifecycle | 3 | All passed |
| test_security.py | Security Testing — Auth, authorization, input validation, SQL injection | 11 | All passed |
| test_ussd.py | Channel Testing — USSD callback (Africa's Talking) | 12 | All passed |
| test_edge_cases.py | Boundary Value & Data Value Testing | 6 | All passed |

### 4.2.4 Testing Strategies Demonstrated

**1. Integration Testing (14 tests):** Full HTTP request → response through FastAPI, testing real endpoint behavior with database interactions. Covers user registration (success + duplicate email rejection), login (success + wrong password), JWT token issuance, report creation with auto-generated reference numbers, report listing with role-based filtering, appointment booking with provider approval flow, and two-way reschedule negotiation.

**2. Security Testing (11 tests):** Unauthenticated access returns 401. Invalid/expired JWT tokens rejected. Community members cannot access provider-only endpoints (403). Report owner isolation (user A cannot read user B's report). Weak passwords rejected at registration (422). Invalid email format rejected. SQL injection attempts in email field rejected. Password hashes never exposed in API responses.

**3. Boundary Value Testing (4 tests):** Report title at exact minimum length (5 chars) accepted. Title one character below minimum rejected. Valid GPS coordinates (-1.9403, 29.8739) accepted. Invalid latitude (999.0) rejected.

**4. Different Data Values (6 tests):** All valid report categories tested (contamination, pipe_burst, low_pressure, no_supply, other). All urgency levels tested (low, medium, high, critical). Rwandan phone number format (+250788123456) accepted. Kinyarwanda names (Uwimana Jean Baptiste) accepted.

**5. USSD Channel Testing (12 tests):** Welcome screen rendering. English and Kinyarwanda language selection. Exit command. Unregistered phone number handling. Wrong PIN rejection. Correct PIN → main menu display. Report category menu. Full report flow (category → urgency → provider → confirm → reference code). Report tracking (empty + populated). Appointment booking flow. Service request flow. Kinyarwanda full report flow.

**6. Error Handling (3 tests):** Nonexistent report returns 403/404. Nonexistent endpoint returns 404. Health check returns `{"status": "ok"}`.

### 4.2.5 Dashboard Synchronization Testing

A comprehensive end-to-end synchronization test was conducted to verify real-time communication between the Community Member and Water Service Provider dashboards. The test confirmed:

1. Community member submits report → Provider sees it instantly on their dashboard
2. Provider acknowledges → Community sees "acknowledged" status immediately
3. Provider sets IN_PROGRESS → Both dashboards and public tracking reflect the change
4. Provider submits resolution with notes → Community sees status + resolution notes
5. Community verifies → Status changes to VERIFIED across all views
6. Service request lifecycle: submitted → acknowledged (bidirectional sync verified)
7. Appointment lifecycle: pending → approved (bidirectional sync verified)

All 7 synchronization tests passed. Both dashboards exchange data through the shared PostgreSQL database, with every status change, resolution note, and notification visible to the other party immediately upon refresh.


---

# CHAPTER FIVE: DESCRIPTION OF THE RESULTS

## 5.1 Problem Recap

In Karangazi Sector, Mbale Cell, Nyagatare District, Rwanda's Eastern Province, community members had no formal digital channel to report water and sanitation infrastructure failures to responsible service providers. Infrastructure failures — affecting 60% of Eastern Province households (NISR, 2025) — went undetected and unresolved for extended periods because complaints relied on informal escalation through local leaders with no tracking, acknowledgement, or accountability mechanism.

## 5.2 Results

### 5.2.1 Platform Capabilities Delivered

The Temba Digital Bridge platform was successfully developed and tested as a fully functional dual-channel system with the following verified capabilities:

**For Community Members (Web + USSD):**
- Registration and authentication via web (email + password + location) and USSD (phone + name + province + district + 4-digit PIN)
- Water issue reporting with category selection, urgency classification, and provider assignment
- Auto-generated tracking codes (RPT-YYYYMMDD-XXXX) for issue follow-up
- Service request submission (water connection, tank delivery, meter support, inspection)
- Appointment booking with date, time, and provider selection
- Password reset via email OTP or phone number
- Issue tracking via web form (no login required) or USSD
- Resolution verification (Verified / Partially Resolved / Not Resolved)
- Anonymous post-verification rating (1–5 stars)
- Full bilingual support (English + Kinyarwanda) across all interfaces

**For Water Service Providers (Web Dashboard):**
- Provider registration with mandatory SLA commitments and escalation contacts
- Admin verification gate (PENDING → APPROVED) with email notification to platform administrator
- Priority-sorted report inbox (P1 Critical → P2 Urgent → P3 Standard) with color-coded badges
- Sequential status management (Open → Acknowledged → In Progress → Resolution Submitted)
- In-app notifications and email alerts for new assignments
- Appointment management with approval/rejection/reschedule workflows
- Aggregate community rating display (★ average/5, total reviews)

**Accountability & SLA Enforcement:**
- Automatic priority classification (P1: 4h SLA, P2: 24h SLA, P3: 72h SLA)
- Hourly Celery Beat SLA monitoring with 2-level email escalation (Officer at 0h, Supervisor at +24h)
- Auto-close of unverified cases after 7 days
- Immutable audit logging of all actions
- Dispute feedback loop (community can reopen cases; 2+ reopens → MANAGEMENT_REVIEW)

### 5.2.2 Testing Outcomes

- **43 automated tests across 7 files:** 100% pass rate
- **6 testing strategies demonstrated:** Integration, security, boundary value, data value, USSD channel, error handling
- **End-to-end synchronization:** 7/7 bidirectional dashboard communication tests passed
- **USSD response time:** 1.6 seconds average through ngrok tunnel (well within AT's 10-second limit)

### 5.2.3 Key Technical Achievements

1. **Dual-channel real-time synchronization:** Reports submitted via USSD appear instantly on the provider's web dashboard, and status updates by providers are immediately visible to community members tracking via the web or USSD.
2. **Stateless USSD architecture:** The entire USSD navigation state is encoded in Africa's Talking's `text` callback parameter — no server-side session storage required, enabling unlimited concurrent USSD sessions without memory scaling concerns.
3. **Anonymous-by-design rating:** The Rating model structurally prevents provider identification of raters by omitting the user_id field entirely from the database schema — anonymity is enforced at the data model level, not through access control alone.
4. **Priority-based SLA enforcement:** The P1/P2/P3 classification matrix uses both category AND urgency (unlike the original category-only SLA), ensuring that a contamination report always gets a 4-hour deadline regardless of user-selected urgency.


---

# CHAPTER SIX: CONCLUSIONS AND RECOMMENDATIONS

## 6.1 Conclusions

The Temba Digital Bridge platform demonstrates that a dual-channel digital reporting system — combining USSD for feature phone users with a web-based platform for smartphone users — can effectively bridge the communication gap between rural Rwandan communities and water service providers. The platform was successfully developed, tested, and verified across all functional requirements, with 43 automated tests achieving 100% pass rate and 7 end-to-end synchronization tests confirming real-time bidirectional communication between community and provider dashboards.

The platform addresses the three core sub-problems identified in the research:
1. **Broken infrastructure goes unreported:** Community members can now report water failures directly to providers via web or USSD, with auto-generated tracking codes and priority-based routing.
2. **No accountability mechanism exists:** The SLA enforcement engine automatically escalates unresolved reports through the provider's internal hierarchy (Officer → Supervisor) via email, with all actions recorded in an immutable audit log.
3. **No communication channel between communities and providers:** Real-time synchronization ensures both parties see the same data simultaneously, and the resolution verification loop gives communities the final say on whether their issue was truly resolved.

## 6.2 Limitations

1. **USSD session timeout:** Africa's Talking enforces a ~30-second timeout per interaction step. While this is standard USSD behaviour, it required simplifying the registration flow from 9+ steps to 5 steps (name → province → district → PIN → confirm PIN) to prevent session expiry during registration.
2. **SMS delivery in sandbox mode:** The Africa's Talking sandbox does not deliver real SMS to actual phone numbers. During development and testing, tracking codes are displayed on the USSD screen itself, and SMS delivery is verified via the AT simulator. Production deployment would require an AT live account with SMS credits (~$1 for 500 messages in Rwanda).
3. **Single-instance deployment:** The current implementation runs on a single server with local PostgreSQL and Redis. Production deployment would require containerized cloud infrastructure (Docker Compose is already configured with NGINX, PostgreSQL, Redis, MinIO, Celery, and Flower services).
4. **Provider verification is manual:** Provider approval currently requires the platform administrator to review a verification email and manually approve via the API. For national scale, an admin dashboard with review workflows would be needed.

## 6.3 Recommendations

1. **Deploy to cloud infrastructure:** Use the existing Docker Compose configuration to deploy to a cloud provider (AWS, Azure, or DigitalOcean) with managed PostgreSQL and Redis for production reliability.
2. **Acquire live Africa's Talking credentials:** Switch from sandbox to a live AT account to enable real SMS delivery and a production USSD shortcode. Cost is approximately $50/month for the shortcode plus ~$0.002 per SMS.
3. **Build admin dashboard:** Create a dedicated admin interface for provider verification, platform analytics, and user management to replace the current email-based approval workflow.
4. **Expand pilot coverage:** After successful pilot in Karangazi Sector, expand to additional sectors in Nyagatare District and then to other Eastern Province districts, leveraging the platform's existing Rwanda-wide administrative hierarchy data.
5. **Integrate with WASAC systems:** Explore data-sharing arrangements with the Water and Sanitation Corporation (WASAC) to feed community-reported infrastructure data into national monitoring systems, creating a complementary bottom-up data source.

## 6.4 Suggestions for Further Research

1. **Longitudinal impact analysis:** Conduct a 6–12 month study measuring the platform's effect on infrastructure response times, community satisfaction, and water point functionality rates before and after deployment.
2. **Machine learning integration:** Develop predictive models using the platform's structured report data to forecast infrastructure failure patterns by season, location, and infrastructure type — enabling proactive maintenance planning.
3. **Expanded geographic scope:** Validate the platform's scalability and adaptability by deploying in districts with different socio-economic and connectivity profiles (e.g., urban Kigali vs. rural Western Province).
4. **Community health integration:** Explore cross-sector applications of the USSD reporting architecture for other community-level service delivery challenges, including sanitation, hygiene, and environmental health monitoring.


---

# References

*(Note: References from Chapters 1-2 of your existing document should be combined with any additional references cited in Chapters 3-6. The references below are only those newly cited in Chapters 3-6 that may not already appear in your Chapter 2 reference list.)*

Yamane, T. (1967). *Statistics: An Introductory Analysis* (2nd ed.). Harper and Row.

*(All other references cited in Chapters 3-6 — NISR (2025), Herschan et al. (2023), Murray et al. (2024), etc. — are already included in your Chapter 2 reference list and should not be duplicated.)*
