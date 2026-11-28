# ReSource

**Intelligent, AI-Powered Circular Campus Resource Exchange and Asset Life Cycle Management System**

COSC 336 Introduction to Software Engineering · Group 3 · Fall 2026

ReSource lets campus departments share assets they no longer need instead of buying new ones or throwing them away. A department registers and publishes an asset, another department requests it, and after release and approval the asset is handed over and its receipt confirmed. Every step is tracked, and a dashboard shows the money, waste and carbon saved.

**Live demo:** <https://rashidcode.pythonanywhere.com>

## Main features

- **Sign-in and roles:** Department Representative, Asset Coordinator and Administrator. The server checks every action against the user's role and department.
- **Assets:** register, publish, search and withdraw, with a full history of every change.
- **Requests:** submit, release, approve, hand over and confirm receipt, with a notification at each step. Nobody can approve a request they submitted or released.
- **Sustainability dashboard:** items reused, cost avoided (AED), waste diverted (kg) and CO2e avoided, each with its formula and source, plus a request report with CSV export.
- **AI support:** suggests an asset's category, condition and tags; ranks the best matches for a need with a score and a reason; and drafts sustainability summaries whose numbers are checked against the calculated figures.

## How a request moves

| Step | Who | New state |
|---|---|---|
| Submit a request | Department Representative | Submitted |
| Release it | Asset Coordinator of the owning department | Released |
| Approve it (units are reserved) | Administrator | Approved |
| Hand the asset over | Asset Coordinator of the owning department | In Transfer |
| Confirm receipt (the asset now belongs to the new department) | Department Representative | Completed |

A request can also be declined, rejected or cancelled, and an open need can be closed with a reason when no match fits.

## AI with a person in charge

- The AI only suggests. A person accepts, edits or rejects every suggestion, and every AI call is saved for audit.
- If the AI is unavailable, every feature falls back to a rule-based result and the page says **"AI unavailable, rule-based result"**.
- Names, e-mail addresses and record codes are removed before any text is sent to the AI.
- Ranking scores come from fixed, documented formulas, so they are the same with or without the AI.

## Built with

Python · Django 5.2 · SQLite · Django templates with plain CSS · Google Gemini through `google-genai` · deployed on PythonAnywhere

## Run it locally

From the `phase6` folder:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed            # empties the database and loads the demo data
python manage.py runserver
```

Open <http://127.0.0.1:8000>. The seed command creates demo users such as `admin`, `eng.coord` and `physics.rep`; see [phase6/README.md](phase6/README.md) for the full list and the demo walkthrough.

The app runs fully without an AI key. To use Gemini, set `GEMINI_API_KEY` in your environment before `runserver`. Never put the key in the code or in Git.

## Tests

```bash
cd phase6
python manage.py test
```

The suite has **124 automated tests, and all pass**: 78 unit, integration and system tests from Phase 6 and 46 black-box and white-box tests from Phase 7. Branch-mode coverage with coverage.py is 94% of statements and 83% of branches. The test cases, oracles and results are in [Phase7/Group3_phase7.pdf](Phase7/Group3_phase7.pdf).

## Repository

Each phase has its own folder, and the working application is in `phase6/`.

| Folder | Contents |
|---|---|
| `phase1/` | Phase 1: project overview, stakeholders, initial requirements and plan |
| `phase2/` | Phase 2: feasibility study, risks and schedule |
| `phase3/` | Phase 3: requirements document |
| `phase4&5/` | Phases 4 and 5: design document |
| `phase6/` | Phase 6: the Django application and its tests |
| `Phase7/` | Phase 7: test document |

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for what each folder contains.

## Team

| Name | Student ID |
|---|---|
| Rashid Alzaabi | 100064869 |
| Mohamed Almarzooqi | 100066203 |
| Mohammad Alsuwaidi | 100064887 |
| Ahmed AlAbdouli | 100062836 |
