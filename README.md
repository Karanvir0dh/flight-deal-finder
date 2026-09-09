# Flight Deal Finder

Production-minded flight-deal discovery and alerting for Toronto-area origins. It runs with deterministic mock data by default and can use documented API providers when credentials are supplied.

## Assumptions And Architecture

Assumptions: prices are normalized to CAD; mock mode must work without credentials; live provider calls are not tested unless you provide keys; Google Flights HTML is never scraped.

Architecture: Typer CLI, FastAPI dashboard/API, SQLAlchemy persistence with Alembic migrations, modular provider adapters, a transparent scoring engine, quota-aware provider selection, idempotent notifications, and GitHub Actions/Docker deployment.

Documented APIs used as of July 26, 2026:

- SerpApi Google Travel Explore API: `GET https://serpapi.com/search.json?engine=google_travel_explore`
- SerpApi Google Flights API: `GET https://serpapi.com/search?engine=google_flights`
- Amadeus OAuth client credentials: `POST /v1/security/oauth2/token`
- Amadeus Flight Inspiration Search: `GET /v1/shopping/flight-destinations`
- Amadeus Flight Offers Search: `GET /v2/shopping/flight-offers`

## Repository Tree

```text
.github/workflows/
alembic/
config/
docs/
src/flight_deals/
tests/
.env.example
docker-compose.yml
Dockerfile
Makefile
pyproject.toml
README.md
SECURITY.md
```

## Beginner Setup

1. Install Python 3.12 from `https://www.python.org/downloads/`.
2. Install Git from `https://git-scm.com/downloads`.
3. Open this folder in a terminal.
4. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

5. Install dependencies:

```powershell
python -m pip install -e ".[dev]"
```

6. Copy the environment example:

```powershell
Copy-Item .env.example .env
```

7. Initialize and seed the database:

```powershell
flight-deals init-db
flight-deals seed-airports
```

8. Run in mock mode:

```powershell
flight-deals run-once --mock --verbose
```

9. Send a simulated exceptional-deal alert:

```powershell
flight-deals test-notification --mock
```

10. Run tests:

```powershell
pytest
```

11. Run linting and type checks:

```powershell
ruff check .
mypy src
```

12. Start the dashboard:

```powershell
uvicorn flight_deals.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/health`.

## Live API Credentials

Set these in `.env` or your deployment secrets:

- `SERPAPI_API_KEY`
- `AMADEUS_CLIENT_ID`
- `AMADEUS_CLIENT_SECRET`
- `ALERT_EMAIL`
- For SMTP: `EMAIL_PROVIDER=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`
- For Resend: `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `RESEND_FROM`
- For Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `DATABASE_URL` for PostgreSQL deployments
- `API_TOKEN` for protected dashboard POST endpoints

## Common Commands

```powershell
flight-deals search --mock --verbose
flight-deals quota --mock
flight-deals coverage
flight-deals providers
flight-deals digest --mock
flight-deals explain-deal --mock
flight-deals feedback 1 --interesting
flight-deals mute DUB --days 90
```

## Docker

```powershell
docker compose up --build
```

The web API listens on `http://localhost:8000`.

## GitHub Actions

The workflow `.github/workflows/scheduled-search.yml` runs every six hours and supports manual dispatch. Add repository secrets for `DATABASE_URL`, provider credentials, and notification credentials. It installs dependencies, runs migrations, executes one quota-aware search cycle, uses concurrency protection, and has a timeout.

## Render Deployment

Current Render docs support Docker web services built from a repository Dockerfile. Create a new Web Service, choose Docker as the runtime/language, connect this repository, set environment variables, configure health check path `/health`, and use the default Docker `CMD`. Render web services must bind to `0.0.0.0` and the expected port is commonly `10000`; override the Docker command with `uvicorn flight_deals.api.app:create_app --factory --host 0.0.0.0 --port $PORT` if Render supplies `PORT`.

## Quotas And Sensitivity

Edit `config/default.yml` for provider monthly quotas, per-run budgets, verification reserves, absolute regional fare thresholds, percentage-drop thresholds, score weights, duplicate cooldown, digest time, origins, trip lengths, and notification levels.

## Troubleshooting

- No credentials: the app automatically falls back to mock mode.
- No email delivered: run `flight-deals test-notification --mock`; console email works without SMTP.
- SQLite path issues: set `DATABASE_URL=sqlite:///./flight_deals.db`.
- Provider errors: run `flight-deals providers` and `flight-deals quota`.
- Duplicate alerts: adjust `notifications.duplicate_cooldown_hours` and resend thresholds.

## Threat Model

Secrets are read from environment variables, logs redact sensitive categories, database queries use SQLAlchemy parameters, external calls use timeouts and TLS verification, manual API mutations require `API_TOKEN`, and tests never call paid live APIs.
