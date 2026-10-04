# Task context: raise backend test coverage to ≥98%

This is the **bracket** tournament-management FastAPI backend. Your job is to **add tests** that
raise code coverage. You write tests only.

## Hard rules
- **Never modify any file under `bracket/`** (the production source). Only add/edit files under `tests/`.
- Do **not** touch `tests/unit_tests/openapi_test.py` (it has a pre-existing, unrelated failure).
- Do not edit `pyproject.toml`, `cov.sh`, or this file.
- Match the existing test style exactly. Keep tests minimal and meaningful — assert real behavior,
  not just "it ran". No redundant tests.

## How to run tests + see coverage
Always use the helper script (it sets the DB env vars and uses the project venv):

```
./cov.sh                                  # full suite + coverage report
./cov.sh tests/unit_tests/foo_test.py     # a single file (faster while iterating)
```

The "Missing" column lists the exact uncovered line numbers. Target those lines.
A Postgres test DB is already running; integration tests work out of the box.

## Where tests live
- **Pure-logic / no-DB tests** → `tests/unit_tests/<name>_test.py`
- **API / DB-touching tests** → `tests/integration_tests/api/<name>_test.py`
- Filenames must end in `_test.py`.

## Conventions (copy these patterns)
- Unit tests: import the function directly and assert. See
  `tests/unit_tests/elimination_test.py`.
- Dummy model instances live in `bracket/utils/dummy_records.py` (e.g. `DUMMY_TEAM1`, `DUMMY_COURT1`,
  `DUMMY_TOURNAMENT`, `DUMMY_MOCK_TIME`). Reuse them with `.model_copy(update={...})`.
- API tests use fixtures `startup_and_shutdown_uvicorn_server` and `auth_context` (an `AuthContext`
  with `.tournament`, `.headers`, `.user`). Helpers from
  `tests/integration_tests/api/shared.py`: `send_tournament_request`, `send_auth_request`,
  `send_request`, `SUCCESS_RESPONSE`.
- DB row context managers from `tests/integration_tests/sql.py`: `inserted_team`, `inserted_court`,
  `inserted_stage`, `inserted_stage_item`, `inserted_round`, `inserted_match`, etc., plus
  `assert_row_count_and_clear`. Study `tests/integration_tests/api/courts_test.py` for the full
  pattern.
- Async tests are decorated `@pytest.mark.asyncio(loop_scope="session")` for API tests; plain async
  defs work for unit tests (`asyncio_mode = auto`).
- `MOCK_NOW` is in `tests/integration_tests/mocks.py`.

## Definition of done for your task
The specific files/lines named in the task prompt are covered, `./cov.sh` for those test files
passes (no failures, no errors), and overall coverage increased. Run the suite at the end to confirm
nothing broke.
