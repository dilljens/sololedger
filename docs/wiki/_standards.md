# Standards

## Rules

- Python 3.11+ required
- Beancount for double-entry accounting
- FastAPI for REST API
- Config via `config.toml`

## Practices

- CLI commands via `python -m app.main <command>`
- Ledger files in Beancount format under `ledger/`
- CSV imports in `imports/`
- Receipt processing via Tesseract OCR

## Patterns

- Module-per-domain under `app/`
- API routes in `app/api.py`
- Tests alongside source (pyproject.toml)
