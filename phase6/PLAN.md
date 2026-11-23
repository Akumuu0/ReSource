# ReSource – Phase 6 Draft Implementation Plan (Group 3)

This plan turns our Phase 4/5 design (`docs/ReSource_Phase4_5_Design_Group3.pdf`) into a
small Django project that covers the Phase 6 features: core features C1–C9 and AI features 1, 2 and 5.
Rule for the whole project: **keep it simple** so that each of us can explain every line in the demo.

## 1. Stack

| Part | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Phase 2 stack |
| Web framework | Django 5.2 (server-rendered templates, plain CSS) | Phase 2 stack (DR-2), built-in login, sessions, password hashing, admin |
| Database | SQLite (one file, `db.sqlite3`) | Draft only; the design's MySQL comes later. The code uses only the Django ORM, so switching is a settings change |
| AI | `google-genai` package, model `gemini-3.5-flash-lite`, key from `GEMINI_API_KEY` | The group chose Gemini; the design's DR-4 named Claude Haiku 5.5 (see section 6) |

`requirements.txt` has only `Django` and `google-genai`.

## 2. Folder structure (one Django app per team area)

```
manage.py
requirements.txt
config/                 Django settings and the main URL list
accounts/               C1 login and roles, C8 notifications           (owner: member 1)
assets/                 C2 register, C3 publish and search, C6 states   (owner: member 2)
resource_requests/      C4 requests, C5 approvals and transfers         (owner: member 3)
sustainability/         C7 dashboard, C9 report table, AI-5 report page (owner: member 4)
ai/                     AIGateway and the three AI services (shared)
templates/              base.html, login page, 403 page
static/css/style.css    the only stylesheet
deploy/                 setup script and WSGI file for putting the site online (README section 6)
docs/                   our earlier documents
```

> The app for requests is called `resource_requests`, not `requests`, because `requests` is the
> name of a well-known Python library and the two would clash on import.

Inside every app the code is split the same way, so it is easy to find things:

| File | What goes in it |
|---|---|
| `models.py` | the database tables (classes from our class diagram) |
| `services.py` | **all business rules** (permission checks, state changes, notifications) |
| `forms.py` | the HTML forms and simple field validation |
| `views.py` | thin functions: read the form, call a service, show a page or an error |
| `urls.py` | the URL list of the app |
| `tests.py` | automated tests for the rules |

## 3. Classes and how they map to our class diagram (design Section 9)

### accounts

| Class | Kind | Design source | Notes |
|---|---|---|---|
| `Department` | model | Fig. 9-1 Department | code, name, campus |
| `User` | model (extends Django `AbstractUser`) | Fig. 9-1 User | one `role` and one `department` per user (simplification of UserRole/Role) |
| `Notification` | model | Fig. 9-6 Notification | recipient, event type, message, link, read time |
| `NotificationService` | service | Notify interface (Fig. 13-1) | creates notifications, counts unread ones |
| `permissions.py` | helpers | AccessCheck interface, access matrix Table 6-2 | `require_role()`, `require_department()`, `@role_required` |
| `common.py` | helpers | Table 16-1 error rule | `BusinessRuleError` (a rule was broken, shown to the user) and `next_code()` |

Roles (Phase 3 names): Department Representative (requester), Asset Coordinator (custodian),
Administrator (approver and admin).

### assets

| Class | Kind | Design source | Notes |
|---|---|---|---|
| `Category` | model | Fig. 9-1 Category | name and keywords (keywords feed the rule-based classifier) |
| `Asset` | model | Fig. 9-1 Asset | code, name, description, category, condition, tags, department, quantity, available quantity, estimated value (AED per unit), weight (kg per unit), repair cost (AED per unit), state, parent (when units are split off) |
| `LifecycleEvent` | model | Fig. 9-3 LifecycleEvent | who, what, when, old state, new state, note. Rows are never updated |
| `AssetStateMachine` | service | State diagram Fig. 12-1 | **the only code that changes `Asset.state`**; refuses any move not in its list |
| `AssetService` | service | Asset operations in Fig. 9-1 and Table 16-1 (`publish`, `withdraw`, `reserve`, `releaseReservation`, `completeTransfer`) | register, edit draft, publish, withdraw, search, reserve units, hand over, complete transfer |

Allowed asset moves (subset of Fig. 12-1):

```
Draft -> Available            publish (owning Asset Coordinator)
Available -> Reserved         final approval reserves the units (Administrator)
Reserved -> In Transfer       hand over (owning Asset Coordinator)
In Transfer -> In Use         receipt confirmed (receiving department)
Reserved -> Available         request cancelled after approval
Available -> Withdrawn        withdraw, only if no open request (owning Asset Coordinator)
```

### resource_requests

| Class | Kind | Design source | Notes |
|---|---|---|---|
| `Request` | model | Fig. 9-1 / 9-2 Request | requester, department, asset (empty for an open need), category, quantity, purpose, needed-by date, specifications, minimum condition, urgency, chosen recommendation, state, reason |
| `Approval` | model | Fig. 9-2 Approval | step (Release or Approval), decision, decided by, reason, time; `is_by(user)` |
| `Transfer` | model | Fig. 9-2 Transfer | the units being moved, from and to department, state, hand-over and receipt details |
| `RequestService` | service | Table 16-1 Requests (`submit`, `cancel`) and Match Review (`decide`) | submit, submit a need, choose a match, reject all matches, cancel, task lists |
| `ApprovalService` | service | Sequence diagram 10.1 | release, decline, approve (reserves units in one transaction), reject |
| `TransferService` | service | Sequence diagram 10.2 | hand over, confirm receipt (owner department changes here) |

Request states (subset of Fig. 12-3): `Open -> Submitted -> Released -> Approved -> In Transfer -> Completed`,
with `Rejected` (decline or reject, always with a reason) and `Cancelled` as end states.

### sustainability

| Class | Kind | Design source | Notes |
|---|---|---|---|
| `CategoryValue` | model | Fig. 9-6 CategoryValue | versioned values per category with source and effective date; used for the emission factor (22.92 kg CO2e/kg, EPA WARM v16), stored for the electronic categories only; a category without a factor is left out of CO2e and shown as missing data (FR-13.8) |
| `SustainabilityImpact` | model | Fig. 9-6 SustainabilityImpact | the frozen figures of one generated report (period, indicator, value, unit) |
| `AIReport` | model | Fig. 9-5 AIReport | draft text, final text, state (Draft, Published, Discarded), who published |
| `SustainabilityCalculator` | service | Section 18 calculation pipeline | the four fixed formulas, never AI |
| `RequestReportService` | service | Table 16-1 `standardReport` | filtered table of requests and transfers, CSV export |

### ai

| Class | Kind | Design source | Notes |
|---|---|---|---|
| `AIOutput` | model | Fig. 9-4 AIOutput | feature, input sent, output, confidence, source (AI or rule-based), note, human decision |
| `Recommendation` | model | Fig. 9-5 Recommendation, Table 17-2 | one ranked candidate of a matching AIOutput, linked to its request (ERD `RECOMMENDATION.request_id`): asset, rank, score, confidence, the eight factor values, reason, strengths, main limitation |
| `AIGateway` | service | Fig. 9-4 AIGateway, Section 4.1 | the **only** class that talks to the AI provider: removes personal data, 20 s timeout, falls back to rules, records every result |
| `ClassificationService` | service | Fig. 9-4 ClassificationService | AI-1: category, condition and tags, each with a confidence; the coordinator accepts or rejects each field (mockup 7.1) |
| `RankingModel` | service | Fig. 9-4 RankingModel, Section 17 | AI-2: the eight weighted factors of Table 17-1, the confidence curve of 17.2, strengths and main limitation of 17.3; the language model only writes the plain-words sentence |
| `ReportGenerator` | service | Fig. 9-4 ReportGenerator, Section 10.5 | AI-5: database figures + AI summary + number check |

## 4. Pages

| URL | Page | Who |
|---|---|---|
| `/login/` | sign in | everyone |
| `/` | home: my role, my department, tasks waiting for me | signed in |
| `/notifications/` | in-app messages (unread count in the header) | signed in |
| `/assets/` | search published assets (keyword, category, condition, department) | signed in |
| `/assets/mine/` | all assets of my department, any state | Asset Coordinator |
| `/assets/new/`, `/assets/<id>/edit/` | register or edit a draft; AI suggestions with Accept / Reject per field (mockup 7.1) | Asset Coordinator |
| `/assets/<id>/` | asset details, buttons, life-cycle history | signed in (drafts: own department and Administrator) |
| `/requests/new/<asset id>/` | request a listed asset | Department Representative |
| `/requests/need/` | describe a need; "Check listings" shows ranked listings beside the form (mockup 7.2) | Department Representative |
| `/requests/<id>/matches/` | top match with its eight factor bars, confidence and reason; Select, choose another with a reason, or reject all (mockup 7.3) | the requester |
| `/requests/mine/` | my requests and their status | Department Representative |
| `/requests/tasks/` | what is waiting for me (release, approve, hand over, confirm receipt) | signed in |
| `/requests/<id>/` | request details, approvals, transfer, action buttons | people involved, Administrator |
| `/sustainability/` | dashboard with 4 measures, each with its formula and source | signed in |
| `/reports/` | requests and transfers table with filters and CSV export | signed in (own department; Administrator sees all) |
| `/reports/summaries/` | AI-generated summaries: generate, edit, publish | Administrator (published ones: everyone) |
| `/admin/` | Django admin (users, roles, data) | Administrator |

## 5. One request from submit to receipt (sequence diagrams 10.1 and 10.2)

1. Department Representative submits (state `Submitted`), the owning Asset Coordinator is notified.
2. Owning Asset Coordinator releases (`Released`) or declines with a reason (`Rejected`, end).
3. An Administrator approves or rejects with a reason. The approver must not be the person who submitted
   or released the request. Approval runs in **one database transaction**:
   a conditional `UPDATE ... SET available = available - n WHERE available >= n` reserves the units.
   If no row is updated, there are not enough units and nothing is saved.
4. The reserved units become their own asset record (state `Reserved`), linked to the original
   (design FR-4.15), and a `Transfer` is created.
5. The owning Asset Coordinator hands over (`In Transfer`).
6. A Department Representative or Asset Coordinator of the receiving department confirms receipt with the
   condition on arrival: the asset becomes `In Use`, its owner department changes, the request is `Completed`.

## 6. Simplifications for the draft (and why)

| Design | Draft | Reason |
|---|---|---|
| MySQL, Docker, Django-Q2 worker, backups, encryption, monitoring | SQLite, `runserver`, no worker | Not needed to show the features |
| Nine roles, UserRole table, consent records | Three roles, one role per user, a `role` field | Phase 6 asks for three roles |
| Second approval by Procurement Team (FR-4.3) | Not built | Desirable requirement; one approval step is enough for C5 |
| Open needs chosen by the Procurement Team (UC-9) | The requester chooses from the AI matches | Procurement Team role is not part of the draft |
| Embedding model and cosine similarity (F1) | Share of the need's words found in the asset text, halved per unmet specification | No extra libraries; anyone can check it by hand |
| F5 ready by the date from expected free dates | Every candidate is free now, so F5 depends only on the needed-by date | Assets are published only when they are free |
| F7 transfer cost from a cost table per route | Fixed sample costs: AED 40 same campus, 120 other campus (Table 17-3); the requester's own department is never a candidate | No transport data in the draft |
| Platt curve refitted per model version | The design's example fit, a = 4.60, b = -2.57 | No labelled evaluation set yet |
| Request page lists matches while typing (7.2) | A "Check listings" button ranks on request | No JavaScript needed |
| DR-4: Claude Haiku 5.5 through the Anthropic API | Gemini (`gemini-3.5-flash-lite`) through the `google-genai` package | The group's choice; only `AIGateway.call_model` and two settings changed, everything else is the same |
| Nine roles in the mockups (Procurement Team, Finance Officer, ...) | Their screens are used by our three roles | Phase 6 asks for three roles |
| Reservation table | The reserved units become their own asset record in state `Reserved` | Same effect, one table less; also gives FR-4.15 (linked record) |
| Partial-unit split at hand-over (FR-4.15) | Split happens at approval | The reserved units need their own state from that moment |
| Disputed transfers, expiry, reminders, maintenance, end of life | Not built | Not in the Phase 6 list |
| Audit log with hash chain | `LifecycleEvent` (asset history) + `Approval` rows + `AIOutput` | Covers "who did what and when" for the demo |
| Nine indicators (Phase 3 Table 2.13-1) | Four: items reused, cost avoided, waste diverted, kg CO2e | Phase 6 asks for at least three |
| "Reserved -> Available (request rejected)" | Only cancellation triggers it | In our flow units are reserved only at final approval, after which nothing can reject the request |
| Notifications sent after commit | Notifications saved in the same transaction | Simpler; still only created when the action succeeds |
| Edit of published assets | Only drafts can be edited | Design FR-1.10 locks fields of reserved assets; the draft locks all published assets |

## 7. Build order

1. C1–C6: accounts, assets, requests, approvals, transfers, state machine, history. Run tests.
2. C7–C9: dashboard, notifications, report table and CSV. Run tests.
3. AI-1, AI-2, AI-5 behind `AIGateway`, each with a rule-based fallback. Run tests.
4. Seed command, README, EXPLAIN, clean-start check.
