# ReSource – Phase 6 Draft Implementation (COSC 336, Group 3)

ReSource is an AI-powered campus resource exchange and asset life-cycle system.
Departments publish surplus assets, other departments request them, the request is released and
approved, the asset is handed over, and the receiver confirms receipt. A dashboard shows the
sustainability impact, and three AI features help along the way.

- Design this code follows: [docs/ReSource_Phase4_5_Design_Group3.pdf](docs/ReSource_Phase4_5_Design_Group3.pdf)
- How the code is organised and what was simplified: [PLAN.md](PLAN.md)
- Plain-English walkthrough for the demo: [EXPLAIN.md](EXPLAIN.md)

Stack: Python 3.12, Django 5.2, SQLite, Django templates with plain CSS, `google-genai` (Gemini) for the AI calls.

## 1. Install and run

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

Windows (PowerShell):

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed
python manage.py runserver
```

Open <http://127.0.0.1:8000> and sign in with one of the demo users below.

`python manage.py seed` **empties the database** and loads the demo data again, so you can run it
before every demo to start clean.

### AI key (optional)

The app works fully without a key: every AI feature then uses its rule-based fallback and shows
**"AI unavailable, rule-based result"**. To use Gemini (model `gemini-3.5-flash-lite`), create a key in
Google AI Studio and set it before `runserver`:

```bash
export GEMINI_API_KEY="your key here"
```

(Windows PowerShell: `$env:GEMINI_API_KEY="your key here"`.) Never put the key in the code, in Git or in a screenshot.

### Run the tests

```bash
python manage.py test
```

74 tests cover the key rules: no self-approval, the last unit cannot be reserved twice, illegal
state moves are refused, permission checks (role and department), the dashboard formulas, the
report and CSV, and the three AI features with and without the AI (including the design's worked
confidence values and the reason needed to choose a match other than the top one).

## 2. Demo logins

Every password is **`demo1234`**. All names are made up.

| Username | Name | Role | Department (campus) |
|---|---|---|---|
| `physics.rep` | Sara Khalid | Department Representative | Physics (SAN Campus) |
| `physics.coord` | Omar Haddad | Asset Coordinator | Physics (SAN Campus) |
| `eng.rep` | Layla Nasser | Department Representative | Engineering (Main Campus) |
| `eng.coord` | Yousef Karim | Asset Coordinator | Engineering (Main Campus) |
| `fac.rep` | Mariam Saeed | Department Representative | Facilities (Main Campus) |
| `fac.coord` | Hassan Ali | Asset Coordinator | Facilities (Main Campus) |
| `admin` | Fatima Rashed | Administrator (also has the `/admin/` site) | Facilities (Main Campus) |

The seed data has 3 departments, 6 categories, 12 assets (including **A-2026-0412 Digital
oscilloscope, 2 units, Good**) and 8 requests in every state:

| Request | State | What to show |
|---|---|---|
| R-2026-0391 | Open | Physics needs 2 oscilloscopes: open the AI matches (AI-2) |
| R-2026-0392, R-2026-0393 | Completed | Counted on the dashboard: 6 items, AED 3,100, 57.0 kg, 206.3 kg CO2e (the monitors: 9.0 kg × 22.92; the chairs have no emission factor and are listed under Missing data) |
| R-2026-0394 | In Transfer | `physics.rep` confirms receipt |
| R-2026-0395 | Released | `admin` approves or rejects |
| R-2026-0396 | Submitted | `eng.coord` releases or declines |
| R-2026-0397 | Rejected | shows the decline reason |
| R-2026-0398 | Approved | `fac.coord` hands it over |

## 3. Suggested demo (about 10 minutes)

1. **`eng.coord`**: Register asset → type a name and description → **Suggest with AI** → **Accept** the category,
   **Reject** the tags → fill quantity, value, weight → **Save draft** → **Publish as surplus**. Show the history table.
2. **`physics.rep`**: Matches and tasks → R-2026-0391 → **See matches**. Explain the eight factor bars (score 91,
   High 0.83) and "How the score works", then **Select** the digital oscilloscope. (Or: New request → fill the
   need → **Check listings** to see the same ranking beside the form.)
3. **`eng.coord`**: Notifications (badge in the header) → open the request → **Release**.
4. **`admin`**: Approvals → open the request: "How this asset was chosen" shows the score and reason →
   **Approve**. The units are reserved and split into their own asset record.
5. **`eng.coord`**: **Mark as handed over**. **`physics.rep`**: **Confirm receipt** → the asset now belongs to
   Physics; open it and show the life-cycle history.
6. **Sustainability** dashboard: four measures, each with its formula and source.
7. **Reports**: filter, then **Export CSV**.
8. **`admin`**: AI summaries → **Generate draft** → edit the text → **Publish**.
9. **No self-approval**: as `admin`, open `/admin/` → Users → `physics.coord` → set Role to
   *Administrator* → Save. Sign in as `physics.coord`, open R-2026-0395 (which `physics.coord` released)
   and press **Approve**: the error *"You released this request, so you cannot also approve or reject it"*
   appears. (The check compares user IDs, so a role change does not get around it.)
10. **Server-side permissions**: as `physics.rep`, open <http://127.0.0.1:8000/assets/new/> by typing the URL:
    the page answers **Not allowed** (HTTP 403), even though the button is not shown.

## 4. Feature checklist

### Core features

| ID | Feature | Where in the code |
|---|---|---|
| C1 | Login and three roles; every action checks role and department on the server | `User.role` and `User.department` in [accounts/models.py](accounts/models.py); `require_role`, `require_department`, `@role_required` in [accounts/permissions.py](accounts/permissions.py); Django's `LoginView` in [accounts/urls.py](accounts/urls.py); every service method starts with a check, e.g. `AssetService.require_owning_coordinator` in [assets/services.py](assets/services.py) |
| C2 | Register an asset (name, description, category, condition, department, quantity, value in AED, weight in kg, repair cost); starts as Draft | `AssetService.register` in [assets/services.py](assets/services.py); `AssetForm` in [assets/forms.py](assets/forms.py); `asset_form` view in [assets/views.py](assets/views.py) |
| C3 | Publish (Draft → Available); search by keyword, category, condition, department | `AssetService.publish` and `AssetService.search` in [assets/services.py](assets/services.py); `SearchForm` in [assets/forms.py](assets/forms.py); page `/assets/` |
| C4 | Submit a request (asset, quantity, purpose, needed-by date) and follow its status | `RequestService.submit` in [resource_requests/services.py](resource_requests/services.py); pages `/requests/mine/` and `/requests/<id>/` |
| C5 | Release by the owning Asset Coordinator, approval by an Administrator, no self-approval, atomic reservation of the last unit, reject with a reason ends the request, receipt changes the owner department | `ApprovalService.release`, `decline`, `approve`, `reject`, `check_not_involved` and `TransferService.hand_over`, `confirm_receipt` in [resource_requests/services.py](resource_requests/services.py); the conditional `UPDATE` in `AssetService.reserve_units` in [assets/services.py](assets/services.py) |
| C6 | Only the allowed state moves; every change writes a LifecycleEvent; history on the asset page | `AssetStateMachine.ALLOWED_MOVES` and `change_state` in [assets/lifecycle.py](assets/lifecycle.py); `LifecycleEvent` in [assets/models.py](assets/models.py); history table in [asset_detail.html](assets/templates/assets/asset_detail.html) |
| C7 | Sustainability dashboard: items reused, cost avoided (AED), waste diverted (kg), kg CO2e (kg × the category's factor: 22.92, EPA WARM v16, for electronics; categories without a factor are listed under Missing data, FR-13.8), each with formula and source | `MEASURES` and `SustainabilityCalculator` in [sustainability/services.py](sustainability/services.py); `CategoryValue.emission_factor` in [sustainability/models.py](sustainability/models.py); page `/sustainability/` |
| C8 | In-app notifications when a request is made, released, approved, rejected, handed over and received; unread count in the header | `Notification` in [accounts/models.py](accounts/models.py); `NotificationService` in [accounts/services.py](accounts/services.py); `notifications` context processor in [accounts/context_processors.py](accounts/context_processors.py); calls in [resource_requests/services.py](resource_requests/services.py) |
| C9 | Report of requests and transfers with filters and CSV export | `RequestReportService` in [sustainability/services.py](sustainability/services.py); `report_table` view in [sustainability/views.py](sustainability/views.py); page `/reports/` |

### AI features

All AI calls go through `AIGateway.run` in [ai/gateway.py](ai/gateway.py): it removes personal data
(`strip_personal_data`), uses a 20-second timeout with no retries, falls back to rules when there is no key,
the call fails or the answer is invalid, and saves an `AIOutput` row ([ai/models.py](ai/models.py)) with the
feature, the text sent, the output, the confidence, the source and later the human decision.

| # | Feature | Where in the code |
|---|---|---|
| AI-1 | Classification (mockup 7.1): suggests category, condition and tags, each with a confidence; the Asset Coordinator accepts, edits or rejects each field; nothing is saved automatically | `ClassificationService` in [ai/classification.py](ai/classification.py) (`suggest`, `check`, `rule_based`, `rows`, `describe_decision`); the suggest / accept / reject / save buttons in `asset_form` in [assets/views.py](assets/views.py); decision saved with `AIOutput.record_decision` |
| AI-2 | Matching and ranking (Section 17, mockups 7.2–7.4): top 5 candidates, eight weighted factors, score 0–100, confidence, strengths, main limitation and a plain-words reason; the requester selects the top match, chooses another with a reason, or rejects all; approvers see how the asset was chosen | `WEIGHTS`, `RankingModel.factors`, `score`, `confidence`, `rank` in [ai/ranking.py](ai/ranking.py) (the language model only writes the sentences); `Recommendation` in [ai/models.py](ai/models.py); `need_create`, `matches`, `choose_match`, `reject_matches`, `request_detail` in [resource_requests/views.py](resource_requests/views.py) |
| AI-5 | Generated report (mockup 7.7): database figures, AI summary with a check mark on every figure, Administrator edits and publishes | `ReportGenerator.generate` and `check_numbers` in [ai/report_generator.py](ai/report_generator.py); `SummaryService.publish` in [sustainability/services.py](sustainability/services.py); `AIReport` and `SustainabilityImpact` in [sustainability/models.py](sustainability/models.py) |

### Tests

| File | What it checks |
|---|---|
| [assets/tests.py](assets/tests.py) | allowed and illegal state moves, history cannot be edited, register / publish / withdraw permissions, search filters |
| [resource_requests/tests.py](resource_requests/tests.py) | full flow, no request for your own department's asset, notifications, partial split, no self-approval, last unit, reject ends the request, cancel, permissions (service and HTTP 403) |
| [sustainability/tests.py](sustainability/tests.py) | dashboard formulas (design worked example: 2 × AED 4,200, 5.2 kg, 119.2 kg CO2e), categories without an emission factor left out of CO2e and listed as missing data, filters, unread badge, report scope, CSV |
| [ai/tests.py](ai/tests.py) | personal-data removal, fallbacks, validation of AI answers, per-field accept and reject, the eight-factor score and confidence, specifications and minimum condition, urgency, reason for choosing another match, a recommendation only answers its own request, own-department assets are not candidates, Rule-based / AI-ranked badge, decisions recorded, number check |
| [accounts/tests.py](accounts/tests.py) | login required, seed command |

## 5. What the draft does not include

Second approval by the Procurement Team, disputes, expiry and reminders, maintenance and end of life,
the hash-chained audit log, embeddings, model registry, backups, encryption, monitoring and a background
worker. PLAN.md, section 6, lists every simplification and the reason for it.

## 6. Put it online (PythonAnywhere, free)

The same code and the same SQLite file run at `https://<username>.pythonanywhere.com`. Only the
settings change, and the WSGI file sets them: [deploy/pythonanywhere_wsgi.py](deploy/pythonanywhere_wsgi.py).
The script [deploy/pythonanywhere.sh](deploy/pythonanywhere.sh) does the rest.

1. Make the upload zip (it leaves out `.venv`, the database and `docs`). Run this from the project folder:

   ```bash
   cd .. && zip -r Resource/resource-upload.zip Resource -x "Resource/.venv/*" "Resource/docs/*" "*/__pycache__/*" "Resource/db.sqlite3" "Resource/staticfiles/*" "*.DS_Store" "Resource/.claude/*" "Resource/resource-upload.zip" "Resource/secret_key.txt" "Resource/ai_key.txt" && cd Resource
   ```

   (Windows: copy the folder without `.venv`, `docs` and `db.sqlite3`, then right-click → Compress to ZIP file.)
2. Sign up at <https://www.pythonanywhere.com> for a free **Beginner** account.
3. **Web** tab → **Add a new web app** → Next → **Manual configuration** → **Python 3.12** → Next.
4. **Files** tab → **Upload a file** → choose `resource-upload.zip`.
5. **Consoles** tab → **Bash**, then run:

   ```bash
   unzip -o resource-upload.zip
   ```

   ```bash
   bash Resource/deploy/pythonanywhere.sh
   ```

   It creates the virtual environment, installs the packages, makes a random secret key
   (`secret_key.txt`, never in the code), runs `migrate`, `collectstatic` and `seed`, and writes the WSGI file.
6. **Web** tab: set **Virtualenv** to `/home/<username>/Resource/.venv`; under **Static files** add URL
   `/static/` with directory `/home/<username>/Resource/staticfiles`; turn on **Force HTTPS**; press **Reload**.
7. Open `https://<username>.pythonanywhere.com` and sign in with a demo login (section 2).

Good to know:

- **Reset the demo data**: run `bash Resource/deploy/pythonanywhere.sh` again, then press Reload.
- **New version of the code**: upload a new zip, repeat step 5, press Reload.
- **Real AI**: put the Gemini API key alone in a file `/home/<username>/Resource/ai_key.txt` (Files tab), then press
  Reload. If a call fails, the app shows the rule-based result, as it does without a key.
- **Keep it running**: on a free account, log in once a month and press **Run until 1 month from today** on the
  Web tab, or the site is switched off on the date shown there.
- **Anyone with the link** can sign in with the demo passwords, including `admin`. That is fine for a class demo;
  reset the data afterwards.
