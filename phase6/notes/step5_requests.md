# Step 5: Requests (Mohammad Alsuwaidi)

Commit: "Add requests: submit, track, cancel and request history (C4, C6)"

- **C4 Submit:** the "Request this asset" button, through
  `RequestService.submit`. Checks the role, that the asset isn't your own,
  that enough units are free, and the date. Then it notifies the owning Asset
  Coordinator.
- **Track:** `/requests/mine/` and `/requests/tasks/`. The request page shows a
  progress bar and the history.
- **Cancel:** only the requester, and only before hand-over.
- **Code:** `resource_requests/services.py`, `views.py`, `urls.py` and the
  templates.
