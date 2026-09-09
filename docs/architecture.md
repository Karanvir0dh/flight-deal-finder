# Architecture

The app separates provider IO, scoring, persistence, scheduling, notifications, and interfaces.

Provider adapters return common domain models. The scoring engine is provider-agnostic and combines absolute thresholds, historical statistics, itinerary quality, confidence, and price momentum. The service layer orchestrates broad discovery, detailed validation, persistence, verification, and idempotent alerts.
