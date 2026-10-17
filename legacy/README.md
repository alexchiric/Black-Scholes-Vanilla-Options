# legacy/

Superseded code kept only for reference (it is also in the git history). Safe to delete.

| File | Replaced by |
|---|---|
| `calculation_workflow.cpp` | `bs_engine.cpp` (batch CSV engine, no `temp.bin`) |
| `vol_smile_workflow.cpp`   | `bs_engine.cpp` + `data_pipeline.vol_smile_pipeline` |
| `app.py`                   | `app_main.py` (Shiny Express app) |

These files no longer compile / run against the corrected core (they use the old string-based API).
