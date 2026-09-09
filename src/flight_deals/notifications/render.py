from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from flight_deals.models.domain import DealCandidate

env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_alert(candidate: DealCandidate) -> tuple[str, str, str]:
    subject = subject_for(candidate)
    html = env.get_template("alert.html").render(candidate=candidate)
    text = env.get_template("alert.txt").render(candidate=candidate)
    return subject, html, text


def subject_for(candidate: DealCandidate) -> str:
    offer = candidate.offer
    if candidate.level.value == "POSSIBLE MISTAKE FARE":
        prefix = "Possible mistake fare"
    elif candidate.level.value == "EXCEPTIONAL":
        prefix = "Exceptional flight deal"
    else:
        prefix = "Great fare found"
    return f"{prefix}: {offer.origin} to {offer.destination} - CAD {offer.price_cad:.0f}"
