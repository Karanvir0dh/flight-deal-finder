# Security

Report private security concerns by opening a private issue or contacting the repository owner directly.

Do not commit `.env`, API keys, SMTP passwords, OAuth tokens, database URLs with passwords, or exported provider responses containing personal data.

Security defaults include environment-based secrets, SQLAlchemy parameterized queries, HTTP timeouts, TLS verification, protected POST endpoints, non-root Docker execution, and no direct Google Flights HTML scraping.
