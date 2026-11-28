# ReSource: Project structure

COSC 336, Group 3. Each phase of the project has its own folder. The combined report of each phase is the `group3_…` (or `Group3_…`) file; the other files are each member's sections and notes.

| Folder | What is inside |
|---|---|
| `phase1/` | Phase 1 report: project overview, stakeholders, initial requirements and plan |
| `phase2/` | Phase 2 feasibility study, risk and schedule, and each member's notes |
| `phase3/` | Phase 3 requirements document, each member's sections and notes |
| `phase4&5/` | Phases 4 and 5 design document, each member's sections and notes |
| `phase6/` | Phase 6: the working Django application and its tests |
| `Phase7/` | Phase 7 test document (`Group3_phase7.pdf`) |

## Inside phase6

| Folder or file | What it does |
|---|---|
| `config/` | Project settings (`settings.py`) and the main URL list (`urls.py`) |
| `accounts/` | Sign-in, roles, departments, permissions and notifications (C1, C8) |
| `assets/` | Register, publish, search and withdraw assets; state machine and history (C2, C3, C6) |
| `resource_requests/` | Requests, releases, approvals and transfers (C4, C5) |
| `sustainability/` | Sustainability dashboard, request report with CSV, and AI summaries (C7, C9) |
| `ai/` | AI gateway, classification, matching and ranking, and summary checks (AI-1, AI-2, AI-5) |
| `templates/`, `static/` | Shared page layout and styles |
| `deploy/` | Setup script and WSGI file for PythonAnywhere |
| `notes/` | Short notes on each implementation step |
| `README.md` | Install steps, demo users and the demo walkthrough |
| `PLAN.md`, `EXPLAIN.md` | How the code is organized, and a plain-English walkthrough |

## Tests

Each app has its Phase 6 tests in `tests.py` and its Phase 7 tests in `test_phase7.py`, next to the code they test.

| File | Tests |
|---|---|
| `accounts/test_phase7.py` | Sign-in, unread count, permissions and CSRF |
| `assets/test_phase7.py` | Request quantity and date, the request form, search and draft editing |
| `resource_requests/test_phase7.py` | Decline reasons, dashboard figures, approval independence, visibility and the summary period |
| `ai/test_phase7.py` | Confidence levels, ranking factors, number check, AI gateway, privacy filter, hidden instructions and the summary page |

## Running phase6

From the `phase6` folder:

1. `python -m venv .venv`
2. Activate it: `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on macOS and Linux
3. `pip install -r requirements.txt`
4. `python manage.py migrate`
5. `python manage.py seed` (empties the database and loads the demo data)
6. `python manage.py runserver`, then open <http://127.0.0.1:8000>

Run the tests with `python manage.py test`. It should end with `Ran 124 tests … OK`.
