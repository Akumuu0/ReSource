\# ReSource: Project structure



COSC 336, Group 3. Each phase of the project has its own folder.



| Folder | What is inside |

|---|---|

| `phase1/` | Phase 1 report and sections |

| `phase2/` | Phase 2 feasibility study, risk and schedule, and each member's notes |

| `phase3/` | Phase 3 requirements sections and notes |

| `phase4\&5/` | Phase 4 and 5 documents |

| `phase6/` | Phase 6: the working Django application |



\## Inside phase6



| Folder | What it does |

|---|---|

| `config/` | Project settings (`settings.py`) and the main URL list (`urls.py`) |

| `accounts/` | Login, roles, departments and notifications (C1, C8) |

| `assets/` | Register, publish and search assets; state machine and history (C2, C3, C6) |

| `resource\_requests/` | Requests, approvals and transfers (C4, C5) |

| `sustainability/` | Sustainability dashboard and request report with CSV (C7, C9) |

| `ai/` | AI classification, matching and summaries (AI-1, AI-2, AI-5) |

| `templates/`, `static/` | Shared page layout and styles |

| `notes/` | Short notes on each implementation step |



\## Running phase6



From the `phase6` folder:



1\. `python -m venv .venv`

2\. `source .venv/Scripts/activate`

3\. `pip install -r requirements.txt`

4\. `python manage.py migrate`

5\. `python manage.py runserver`



Run the tests with `python manage.py test`.

