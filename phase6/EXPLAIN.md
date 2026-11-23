# How ReSource works – a walkthrough for the demo

This file explains the code in plain English, so that each of us can answer questions about any part.

## 1. The big picture

ReSource is one Django project. Django splits every page into three parts:

- a **URL** (in `urls.py`) says which function handles an address such as `/requests/5/`;
- a **view** (in `views.py`) is that function: it reads the form, calls our code, and picks a template;
- a **template** (an `.html` file) turns the data into the page the user sees.

We added one more layer, the **services** (`services.py`). They hold every business rule. Views are
deliberately thin: they never change the database themselves, they ask a service to do it. This is why
the instructor's rule "the code is structured into classes" is met: the rules live in classes such as
`ApprovalService`, `AssetStateMachine` and `AIGateway`, not in the views and not in one big file.

```
Browser ──► urls.py ──► views.py ──► services.py ──► models.py ──► SQLite
                           │              (rules,        (tables)
                           │            permissions,
                           ▼            notifications)
                     templates/*.html
```

## 2. The five apps (one per team member)

| App | What it does | Main classes |
|---|---|---|
| `accounts` | sign-in, roles, departments, notifications | `User`, `Department`, `Notification`, `NotificationService` |
| `assets` | register, publish, search, state machine, history | `Asset`, `Category`, `LifecycleEvent`, `AssetService`, `AssetStateMachine` |
| `resource_requests` | requests, release, approval, hand-over, receipt | `Request`, `Approval`, `Transfer`, `RequestService`, `ApprovalService`, `TransferService` |
| `sustainability` | dashboard, report table and CSV, AI summaries | `CategoryValue`, `SustainabilityImpact`, `AIReport`, `SustainabilityCalculator`, `RequestReportService` |
| `ai` | everything that talks to the AI | `AIGateway`, `AIOutput`, `ClassificationService`, `RankingModel`, `ReportGenerator` |

The class names are the names in our class diagram (design Section 9). PLAN.md maps each one to its figure.

Two small shared files in `accounts` are used by everyone:

- `accounts/permissions.py` – `require_role(user, ...)` and `require_department(user, department)`.
  If the check fails they raise Django's `PermissionDenied`, and the user gets the **Not allowed** page (HTTP 403).
- `accounts/common.py` – `BusinessRuleError`, the error a service raises when a rule is broken
  ("not enough units", "a reason is required"). Views catch it and show it as a red message.

## 3. The three roles and how permissions are checked

Each user has one `role` and one `department` (fields on `User`):

| Role | Can do |
|---|---|
| Department Representative | request assets, describe needs, choose AI matches, cancel own requests, confirm receipt for own department |
| Asset Coordinator | register, publish, withdraw own department's assets; release or decline requests for them; hand them over; confirm receipt for own department |
| Administrator | approve or reject released requests; generate and publish AI summaries; Django admin site |

Permissions are checked **twice**:

1. In the **view**, `@role_required(User.COORDINATOR)` stops the wrong role from even opening a page.
2. In the **service**, every method checks again, including the department. For example
   `ApprovalService.release` calls `AssetService.require_owning_coordinator(user, request.asset)`.

The second check is the one that matters: even if someone builds a fake form and posts it to
`/requests/5/approve/`, the service refuses. Hiding a button in the template is only for comfort.

## 4. One request, from submit to receipt

We follow R-2026-0391: Physics needs 2 oscilloscopes; Engineering owns A-2026-0412.

### Step 1 – Submit (Department Representative)

`physics.rep` either clicks **Request this asset** on an asset page, or describes a need and picks an AI match.

- View: `request_create` (or `choose_match`) in `resource_requests/views.py`.
- Service: `RequestService.submit` checks:
  - the user is a Department Representative (`require_role`);
  - the asset does not already belong to the user's department (`check_not_own`: "This asset already belongs
    to your department"; the transfer would change nothing). The page also hides the button for them;
  - the asset is Available and has enough free units (`check_units`);
  - the needed-by date is not in the past (`check_date`).
- It saves a `Request` with state **Submitted**. The requesting department is always taken from the user,
  never from the form.
- `notify_new_request` sends a notification to the Asset Coordinator(s) of Engineering.

### Step 2 – Release or decline (owning Asset Coordinator)

`eng.coord` sees the request under **My tasks → Release or decline**.

- `ApprovalService.release` checks the user is the Asset Coordinator of the asset's department and that the
  request is still Submitted (`require_state`). It saves an `Approval` row (step *Release*, decision
  *Approved*), sets the request to **Released**, and notifies the requester and all Administrators.
- `ApprovalService.decline` needs a reason (`require_reason`), saves an `Approval` with decision *Rejected*,
  sets the request to **Rejected** and notifies the requester.

### Step 3 – Approve or reject (Administrator)

`admin` sees the request under **My tasks → Approve or reject**.

- `ApprovalService.check_not_involved` refuses if this user **submitted** the request or **made any earlier
  decision** on it (`Approval.is_by(user)`). It compares user IDs, so changing someone's role later does not
  get around the rule. The user sees a clear red message.
- `ApprovalService.approve` is wrapped in `@transaction.atomic`: everything inside happens completely or not at
  all. Inside it:
  1. `AssetService.reserve_units` reserves the units (see section 6);
  2. an `Approval` row is saved;
  3. a `Transfer` row is created (state *Scheduled*);
  4. the request becomes **Approved**;
  5. the requester and the owning coordinator are notified.
  If step 1 fails (not enough units), nothing at all is saved.
- `ApprovalService.reject` needs a reason and sets the request to **Rejected**.

**Nothing runs after a reject**: every later method begins with `require_state(...)`, and Rejected is not
an allowed starting state for any of them.

### Step 4 – Hand over (owning Asset Coordinator)

- `TransferService.hand_over` checks the owning coordinator and the Approved state, moves the asset
  **Reserved → In Transfer** through the state machine, sets the transfer and the request to *In Transfer*,
  and asks the requester to confirm receipt.

### Step 5 – Confirm receipt (receiving department)

- `TransferService.confirm_receipt` only accepts a Department Representative or Asset Coordinator of the
  **receiving** department (`require_receiver`) and requires the condition on arrival.
- `AssetService.complete_transfer` changes the asset's **owner department** to Physics, stores the condition
  and moves it **In Transfer → In Use**.
- The transfer becomes *Received*, the request **Completed**, and the old owner and the Administrators are
  notified. Only now does the dashboard count the reuse.

## 5. The asset state machine

`assets/lifecycle.py` has one class, `AssetStateMachine`, with one set:

```python
ALLOWED_MOVES = {
    ("Draft", "Available"),        # publish
    ("Available", "Reserved"),     # approval reserves the units
    ("Reserved", "In Transfer"),   # hand over
    ("In Transfer", "In Use"),     # receipt confirmed
    ("Reserved", "Available"),     # request cancelled after approval
    ("Available", "Withdrawn"),    # withdraw
}
```

`change_state(asset, new_state, user, action)` is the **only** code in the project that changes
`asset.state`. If `(old, new)` is not in the set it raises `BusinessRuleError` and nothing changes.
Otherwise it saves the asset and writes a `LifecycleEvent` with **who** (`performed_by`), **what** (`action`),
**when** (`occurred_at`), the **old state** and the **new state**. `LifecycleEvent.save` refuses to update an
existing row, so history cannot be edited. The asset page shows these rows as its history table.

## 6. Why the last unit can never go to two requests

Imagine two Administrators approving two different requests for the **last** oscilloscope at the same moment.
If the code did "read the free units, check, then write", both could read "1 free" and both could succeed.

`AssetService.reserve_units` instead asks the database to do the check and the change in **one** statement:

```python
updated_rows = Asset.objects.filter(
    pk=asset.pk, state="Available", available_quantity__gte=quantity
).update(available_quantity=F("available_quantity") - quantity)
```

In SQL this is `UPDATE asset SET available_quantity = available_quantity - 2 WHERE id = 12 AND
available_quantity >= 2`. The database runs such updates one at a time on the same row, so the second one
finds `available_quantity = 0`, matches **0 rows**, and we raise "Not enough units". Because we are inside
`transaction.atomic`, the half-finished approval is rolled back. The test
`test_last_unit_can_never_go_to_two_requests` proves this.

**Partial requests**: if a request takes 2 of 5 chairs, the 2 reserved chairs get their own `Asset` record
(new code, `parent` pointing to the original, state Reserved) and the original keeps 3. This follows design
FR-4.15 and lets each record have one clear state and one owner.

## 7. Notifications (C8)

`NotificationService.notify(users, event_type, message, link)` saves one `Notification` row per user. The
services call it when a request is made, released, approved, rejected, handed over, received or cancelled.
`accounts/context_processors.py` adds `unread_count` to every page, and `base.html` shows it as the yellow
badge. Opening **Notifications** lists them; **Mark all as read** fills `read_at`.

## 8. The sustainability dashboard (C7)

`SustainabilityCalculator.calculate()` loops over every `Transfer` with state *Received* (only completed
transfers count) and adds up, per transfer:

| Measure | Formula |
|---|---|
| Items reused | units |
| Cost avoided (AED) | units × replacement value per unit |
| Waste diverted (kg) | units × weight per unit |
| kg CO2e avoided | kg diverted × the category's emission factor |

The 22.92 kg CO2e per kg is the EPA WARM version 16 factor for **mixed electronics** (design Section 18). It is
stored as a `CategoryValue` (with its source, date and version) **only for the electronic categories**: Lab
Equipment, Computers & Monitors and Audio-Visual. Furniture, Office Equipment and Tools & Workshop have no factor,
because an electronics factor would be wrong for a chair.

**Missing data rule (FR-13.8):** when a transfer's category has no emission factor, `CategoryValue.emission_factor`
returns `None`, the transfer is **left out of the CO2e total**, and the dashboard lists it under **"Missing data"**
with a count. It still counts as items reused, AED and kg. There is no default factor.

The `MEASURES` list holds each formula and source, and the page prints them. No AI is used for any number.

Example (seed data): 2 monitors (AED 650, 4.5 kg each) + 4 chairs (AED 450, 12 kg each) =
6 items, AED 3,100, 57.0 kg. CO2e counts only the monitors: 9.0 kg × 22.92 = **206.3 kg CO2e**; the chairs
(Furniture) appear under "Missing data · 1 transfer(s) left out of CO2e".

## 9. The report page (C9)

`RequestReportService.requests_for(user, filters)` returns the requests the user may see (Administrators:
all; others: requests made by or sent to their department) with the chosen filters. The same list is shown as
a table or, with `?export=csv`, written with Python's `csv` module and downloaded.

## 10. The AI features

### The gateway – the only door to the AI

`AIGateway.run(feature, system, prompt, schema, fallback, user, validate)` in `ai/gateway.py` does five things
for every AI call:

1. **Removes personal data** (`strip_personal_data`): e-mails, record codes like A-2026-0412, long numbers
   (university IDs) and the names and usernames of registered users. The services also only put the needed
   text in the prompt: no names, no IDs.
2. **Calls Gemini** (`call_model`) with model `gemini-3.5-flash-lite`, a **20-second timeout** and no retries
   (`HttpRetryOptions(attempts=1)`). We ask for JSON that follows a schema (`response_json_schema`), so the
   answer is easy to read.
3. **Checks the answer** with the service's `validate` function (for example: is the category on our list?).
4. **Falls back** to the service's rule-based `fallback` if there is no key, the call fails or times out, or
   the answer is invalid. The page then shows **"AI unavailable, rule-based result"** and the reason.
5. **Records** an `AIOutput` row: feature, the exact text sent, the output, confidence, source and note.
   When the person later accepts, edits, rejects or publishes, `AIOutput.record_decision` stores the
   **human decision**, who made it and when.

The app works completely without a key; every test runs without one.

Because only `call_model` talks to the provider, changing from Claude (the design's DR-4) to Gemini meant
changing that one method and two settings (`GEMINI_API_KEY`, `AI_MODEL`); no service, page or test changed.

### AI-1 Classification (`ai/classification.py`) – design mockup 7.1

On the register form the coordinator presses **Suggest with AI**. `ClassificationService.suggest` sends the
name, description and the list of approved categories, and gets back category, condition and tags, **each with
its own confidence**, plus an overall confidence and a reason. The panel beside the form shows one row per field
with **Accept** and **Reject** buttons (and **Accept all**). Accept copies only that value into the form; Reject
keeps what was typed. Two hidden inputs (`accepted`, `rejected`) remember the choices between clicks. Nothing is
saved until **Save draft**. On save, `describe_decision` records what happened to each field, for example
"Category accepted; condition edited (Good -> Fair); tags rejected".

Fallback: count each category's keywords in the text (`Category.keywords`), look for condition words such as
"broken" (Poor) or "unused" (New), and use the matched keywords as tags. Its confidences are simple rules:
category 0.3 + 0.15 per keyword found (at most 0.7), condition 0.6 if a condition word was found (else 0.3),
tags 0.5 if keywords were found (else 0.3).

### AI-2 Matching and ranking (`ai/ranking.py`) – design Section 17, mockups 7.2 to 7.4

A Department Representative describes a need: category, purpose, quantity, date, urgency, minimum condition and
specifications ("At least 70 MHz, 2 channels"). **Check listings** ranks without saving; **Submit as open need**
saves it and opens the matches page.

`RankingModel.rank` takes the candidates (published assets of **other** departments with free units, in the
requested category or sharing a word with the need; the requester's own assets are left out because moving them
changes nothing) and scores each one with the **eight factors of design Table 17-1**:

```python
WEIGHTS = {"function": 0.35, "quantity": 0.15, "condition": 0.10, "location": 0.10,
           "ready": 0.10, "repair": 0.08, "transfer": 0.07, "carbon": 0.05}
score = round(100 * sum(weight * factor))   # each factor is between 0 and 1
confidence = 1 / (1 + e^-(4.60 * score/100 - 2.57))   # High from 0.80, Medium from 0.50
```

| Factor | Value |
|---|---|
| F1 function and specs | share of the need's words (purpose + specifications) found in the asset text, halved for each specification the asset does not meet (it states 50 MHz, you asked for at least 70 MHz) |
| F2 quantity | free units ÷ units needed (at most 1) |
| F3 condition | New 1.0, Good 0.9, Fair 0.6, Poor 0.3; at most 0.3 if below the minimum asked for |
| F4 location | same campus 0.85, other campus 0.55 |
| F5 ready by the date | 1.0 if free by the date (all candidates are free now), 0.5 if up to 2 days late, else 0 |
| F6 repair cost | 1 − repair cost ÷ value |
| F7 transfer cost | 1 − moving cost ÷ (0.15 × value); moving costs AED 40 on the same campus, 120 to another campus |
| F8 waste and carbon | kg CO2e saved ÷ the largest kg CO2e among the candidates (0 if the category has no emission factor) |

High urgency doubles the F5 weight and Low halves it; the weights are then rescaled to add up to 1.
The **strengths** are the three largest `weight × factor`; the **main limitation** is the largest
`weight × (1 − factor)`, written in plain words ("on another campus, so moving it costs about AED 120").

#### Worked example: why the top match for R-2026-0391 scores 91 with confidence 0.83

The need (seed data): Physics (SAN Campus) wants **2** units of Lab Equipment, purpose "Two oscilloscopes for the
teaching lab", specifications "At least 70 MHz, 2 channels", minimum condition Good, urgency Medium.
The candidate: **A-2026-0412 Digital oscilloscope**, Engineering (Main Campus), Good, 2 free units,
AED 4,200 and 2.6 kg per unit, no repairs. The other candidate is the bench power supply A-2026-0407
(Physics' own analog oscilloscope is not a candidate).

**Step 1 – the eight factor values** (each between 0 and 1, rounded to 2 decimals):

| Factor | How | Value |
|---|---|---|
| F1 function and specs | need words *oscilloscope, teaching, mhz, channel*: all 4 are in the asset text → 4 ÷ 4 = 1.0; "70 MHz" is met (it has 100 MHz); "2 channels" has no number in the asset text, so it is not checked → × 0.5⁰ | 1.00 |
| F2 quantity | min(2 free, 2 needed) ÷ 2 | 1.00 |
| F3 condition | Good = 0.90; not below the Good minimum | 0.90 |
| F4 location | Main Campus vs SAN Campus = other campus | 0.55 |
| F5 ready by the date | free now, needed in 3 weeks | 1.00 |
| F6 repair cost | no repairs: 1 − 0 ÷ 4,200 | 1.00 |
| F7 transfer cost | 1 − 120 ÷ (0.15 × 4,200) = 1 − 120 ÷ 630 | 0.81 |
| F8 waste and carbon | 2 × 2.6 kg × 22.92 = 119.2 kg CO2e; the largest candidate (power supply) saves 2 × 4 kg × 22.92 = 183.4 → 119.2 ÷ 183.4 | 0.65 |

**Step 2 – multiply by the weights and add up** (urgency Medium, so the weights are unchanged):

| Factor | Weight × value | = |
|---|---|---|
| F1 | 0.35 × 1.00 | 0.3500 |
| F2 | 0.15 × 1.00 | 0.1500 |
| F3 | 0.10 × 0.90 | 0.0900 |
| F4 | 0.10 × 0.55 | 0.0550 |
| F5 | 0.10 × 1.00 | 0.1000 |
| F6 | 0.08 × 1.00 | 0.0800 |
| F7 | 0.07 × 0.81 | 0.0567 |
| F8 | 0.05 × 0.65 | 0.0325 |
| **Sum** | | **0.9142** |

**Step 3 – the score:** round(100 × 0.9142) = round(91.42) = **91**.

**Step 4 – the confidence:** S = 91 ÷ 100 = 0.91, so 4.60 × 0.91 − 2.57 = 1.616 and
1 ÷ (1 + e^−1.616) = 1 ÷ (1 + 0.199) = **0.83**, which is **High** (0.80 or more).

**Step 5 – strengths and limitation:** the three largest weight × value are F1 (0.35), F2 (0.15) and F5 (0.10);
the largest gap weight × (1 − value) is F4: 0.10 × 0.45 = 0.045, so the main limitation is "on another campus,
so moving it costs about AED 120". The design's own example (with embeddings) gives 92 and 0.84.

Each of the top 5 is saved as a `Recommendation` row (design Fig. 9-5) under the `AIOutput`, together with the
request it was ranked for (`Recommendation.request`, ERD `RECOMMENDATION.request_id`; empty for "Check listings",
which ranks a need that is not saved yet). `RequestService.choose_match` refuses a recommendation that belongs to
another request. **The AI only writes the "in plain words" sentence**; it never changes the score or the order.
The badge says **AI-ranked** only when the AI wrote those sentences, and **Rule-based** when the fallback did. The requester presses
**Select** on the top match, or **Choose this** on another one with a required reason (FR-8.7,
`RequestService.choose_match`), or **Reject all** with a reason. The chosen recommendation is stored on the
request (`Request.recommendation`), so the release and approval page shows "How this asset was chosen":
score, confidence, rank and reason, "for information only".

### AI-5 Generated report (`ai/report_generator.py`)

1. `SustainabilityCalculator` calculates the four numbers for the chosen period.
2. The AI gets only those numbers and writes 2–3 sentences.
3. `check_numbers` finds every number in the AI text and compares it with the calculated numbers (and the
   period dates). One unknown number is enough to throw the AI text away and use the template text instead.
4. The draft is saved as an `AIReport` with its figures frozen as `SustainabilityImpact` rows.
5. The Administrator edits the text and presses **Publish** (`SummaryService.publish`), or **Discard**.
   Only published summaries are visible to other users.

## 11. Seed data and tests

- `python manage.py seed` (`accounts/management/commands/seed.py`) empties the database and creates the demo
  data **by calling the real services**, so every seeded request has real approvals, history and notifications.
- `python manage.py test` runs 74 tests. Each test builds a small world with `accounts/sample_data.py`
  (Physics, Engineering, Facilities, six users, one oscilloscope) and checks one rule. AI tests never call the
  real AI: there is no key, or `AIGateway.call_model` is replaced by a fake answer.

## 12. Questions we may be asked

**Why services and not logic in the views?** One place per rule, easy to test without a browser, and the same
rule applies whether the action comes from a page, the seed command or a test.

**What stops someone approving their own request?** `ApprovalService.check_not_involved`, on the server,
comparing user IDs. The test `test_releaser_cannot_also_approve` changes a coordinator into an Administrator and
shows it still fails.

**What happens if the AI is down?** The gateway's fallback runs and the page says "AI unavailable, rule-based
result". Every feature still works.

**Can the AI change data?** No. It only returns suggestions. A person must press Save, Select or Publish, and
the normal service checks run then.

**Why is our match score not exactly the design's 92?** The design's F1 uses an embedding model (cosine
similarity). We use word overlap instead, so no extra library is needed and anyone can check it by hand. The
other seven factors, the weights and the confidence formula are the design's.

**Why SQLite?** The draft runs on one laptop with no setup. The code only uses the Django ORM, so moving to the
design's MySQL is a change in `config/settings.py`.

**Where is the password stored?** Django's `create_user` stores only a salted PBKDF2 hash (design Table 6-4).
