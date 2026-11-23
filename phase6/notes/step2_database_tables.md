# Step 2: Database tables (Mohammad Alsuwaidi)

Commit: "Add the database tables and migrations for assets, requests and AI"

- **assets:** Category, Asset, LifecycleEvent (`assets/models.py`)
- **resource_requests:** Request, Approval, Transfer (`resource_requests/models.py`)
- **ai:** AIOutput, Recommendation (`ai/models.py`)
- The `migrations/` folders create these tables. Run `python manage.py migrate`.
- Every table has an automatic `id` primary key. Readable codes like
  `A-2026-0412` and `R-2026-0391` are separate unique columns.
- Also registered the three apps in `config/settings.py`.
