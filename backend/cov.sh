#!/bin/bash
# Helper: run the test suite with coverage using the CI database.
# Usage: ./cov.sh [extra pytest args]   e.g.  ./cov.sh tests/unit_tests/logger_test.py
set -o pipefail
export PATH="$HOME/.local/bin:$PATH"
export PG_DSN='postgresql://bracket_ci:bracket_ci@localhost:5532/bracket_ci'
export JWT_SECRET='abd84ebeb6581c26b53fa30d89c4e7fbc48ee5b4f3b8ddedb7586cfeb3daca0c'
export CORS_ORIGINS='*'
export ADMIN_EMAIL='admin@example.com'
export ADMIN_PASSWORD='x'
export ENVIRONMENT=CI
uv run pytest --cov=bracket --cov-report=term-missing -o addopts="" -p no:randomly "$@"
