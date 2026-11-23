# Step 3: Assets (Mohammad Alsuwaidi)

Commit: "Add assets: register, publish, search, state machine and history (C2, C3, C6)"

- **C2 Register:** `/assets/new/`, through `AssetService.register`. Saves a
  Draft in the coordinator's own department.
- **C3 Publish and search:** `AssetService.publish` makes all units available.
  `/assets/` searches published assets by keyword, category, condition and
  department.
- **C6 States and history:** `assets/lifecycle.py`. Only six state moves are
  allowed, and each one writes a `LifecycleEvent` that cannot be edited.
- **Tests:** `assets/tests.py` (10 tests).
