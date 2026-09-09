# Deployment

Local: use the Typer CLI with SQLite or PostgreSQL.

GitHub Actions: add secrets and use the scheduled workflow.

Docker: run `docker compose up --build`.

Render: create a Docker web service from the repository Dockerfile, set environment variables, set health check path `/health`, and ensure the command binds to `0.0.0.0:$PORT`.
