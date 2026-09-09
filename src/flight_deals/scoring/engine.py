from __future__ import annotations

from statistics import mean, median

from flight_deals.config.settings import AppConfig
from flight_deals.models.domain import (
    BookingConfidenceLevel,
    DealCandidate,
    DealLevel,
    FlightOffer,
    HistoricalStats,
    VerificationResult,
)

REGION_BY_AIRPORT = {
    "DUB": "europe",
    "LIS": "europe",
    "SAN": "united_states",
    "LAX": "united_states",
    "MEX": "mexico_caribbean_central_america",
    "BOG": "south_america",
    "NRT": "asia",
    "SYD": "oceania",
}


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(round((len(ordered) - 1) * pct), 0), len(ordered) - 1)
    return ordered[index]


class DealScorer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def historical_stats(
        self,
        offer: FlightOffer,
        route_prices: list[float],
        last_alert_price: float | None = None,
    ) -> HistoricalStats:
        if not route_prices:
            return HistoricalStats(observation_count=0)
        med = median(route_prices)
        recent_low = min(route_prices[-30:]) if route_prices[-30:] else min(route_prices)
        deviations = [abs(v - med) for v in route_prices]
        mad = median(deviations) or 1
        return HistoricalStats(
            median_price=med,
            mean_price=mean(route_prices),
            min_price=min(route_prices),
            p10_price=percentile(route_prices, 0.10),
            p25_price=percentile(route_prices, 0.25),
            seven_day_median=median(route_prices[-7:]),
            thirty_day_median=median(route_prices[-30:]),
            ninety_day_median=median(route_prices[-90:]),
            percent_below_route_median=max((med - offer.price_cad) / med * 100, 0),
            percent_below_recent_lowest=max((recent_low - offer.price_cad) / recent_low * 100, 0),
            price_change_since_last_observation=offer.price_cad - route_prices[-1],
            price_change_since_last_alert=(
                offer.price_cad - last_alert_price if last_alert_price is not None else None
            ),
            robust_anomaly_score=(med - offer.price_cad) / (1.4826 * mad),
            observation_count=len(route_prices),
        )

    def score(
        self,
        offer: FlightOffer,
        route_prices: list[float] | None = None,
        verification: VerificationResult | None = None,
        last_alert_price: float | None = None,
    ) -> DealCandidate:
        route_prices = route_prices or []
        stats = self.historical_stats(offer, route_prices, last_alert_price)
        region = REGION_BY_AIRPORT.get(offer.destination, "europe")
        threshold_map = (
            self.config.thresholds.one_way
            if offer.trip_type == "one_way"
            else self.config.thresholds.round_trip
        )
        absolute_threshold = threshold_map.get(region, max(threshold_map.values()))
        weights = self.config.scoring.weights
        score = 0.0
        score += min(
            max((absolute_threshold / max(offer.price_cad, 1)) * 16, 0),
            weights["absolute_affordability"],
        )
        if stats.percent_below_route_median is not None:
            score += min(
                stats.percent_below_route_median / 50 * weights["median_discount"],
                weights["median_discount"],
            )
        if stats.p10_price and offer.price_cad <= stats.p10_price:
            score += weights["historical_rarity"]
        elif stats.p25_price and offer.price_cad <= stats.p25_price:
            score += weights["historical_rarity"] * 0.65
        score += self._quality_points(offer)
        confidence_score, confidence_level = self._booking_confidence(offer, verification)
        score += confidence_score / 100 * weights["booking_confidence"]
        if (
            stats.price_change_since_last_observation
            and stats.price_change_since_last_observation < 0
        ):
            score += min(
                abs(stats.price_change_since_last_observation)
                / 100
                * weights["price_drop_momentum"],
                weights["price_drop_momentum"],
            )
        score -= self._penalties(offer, verification)
        score_i = max(0, min(round(score), 100))
        level = self._level(score_i, offer, absolute_threshold, stats)
        explanation = self._explain(score_i, offer, stats, level, verification)
        return DealCandidate(
            offer=offer,
            score=score_i,
            level=level,
            explanation=explanation,
            booking_confidence_score=confidence_score,
            booking_confidence_level=confidence_level,
            historical_stats=stats,
            verification=verification,
        )

    def _quality_points(self, offer: FlightOffer) -> float:
        base = self.config.scoring.weights["itinerary_quality"]
        if offer.stops == 0:
            return base
        if offer.stops == 1:
            return base * 0.75
        return base * 0.45

    def _booking_confidence(
        self, offer: FlightOffer, verification: VerificationResult | None
    ) -> tuple[int, BookingConfidenceLevel]:
        score = 20
        if offer.includes_taxes:
            score += 15
        if offer.booking_link:
            score += 20
        if offer.segments or offer.raw_provider_id:
            score += 15
        if verification and verification.status != "Unverified":
            score += 20
        if offer.currency == "CAD" and offer.price_cad > 0:
            score += 10
        level = (
            BookingConfidenceLevel.HIGH
            if score >= 75
            else BookingConfidenceLevel.MEDIUM
            if score >= 45
            else BookingConfidenceLevel.LOW
        )
        return min(score, 100), level

    def _penalties(self, offer: FlightOffer, verification: VerificationResult | None) -> float:
        penalties = self.config.scoring.penalties
        total = 0.0
        if offer.self_transfer:
            total += penalties["self_transfer"]
        if offer.mixed_airports:
            total += penalties["airport_change"]
        if offer.separate_tickets:
            total += penalties["separate_tickets"]
        if offer.stops > 1:
            total += penalties["more_than_one_stop"]
        if offer.total_duration_minutes > 18 * 60:
            total += penalties["very_long_duration"]
        if offer.basic_economy:
            total += penalties["basic_economy"]
        if not offer.baggage:
            total += penalties["missing_baggage"]
        if not verification:
            total += penalties["unverified"]
        return total

    def _level(
        self, score: int, offer: FlightOffer, absolute_threshold: float, stats: HistoricalStats
    ) -> DealLevel:
        exceptional_abs = offer.price_cad <= absolute_threshold
        if score >= 88 and (exceptional_abs or (stats.percent_below_route_median or 0) >= 50):
            return DealLevel.POSSIBLE_MISTAKE_FARE
        if score >= 78 or exceptional_abs:
            return DealLevel.EXCEPTIONAL
        if score >= 65:
            return DealLevel.GREAT
        if score >= 50:
            return DealLevel.GOOD
        return DealLevel.WATCH

    def _explain(
        self,
        score: int,
        offer: FlightOffer,
        stats: HistoricalStats,
        level: DealLevel,
        verification: VerificationResult | None,
    ) -> str:
        pieces = [
            f"Score {score}/100: CAD {offer.price_cad:.0f} {offer.origin}-{offer.destination}"
        ]
        pieces.append("one way" if offer.return_date is None else "round trip")
        if stats.percent_below_route_median is not None:
            pieces.append(f"{stats.percent_below_route_median:.0f}% below route median")
        if stats.min_price is not None and offer.price_cad < stats.min_price:
            pieces.append("new observed low")
        pieces.append(f"{offer.stops} stop{'s' if offer.stops != 1 else ''}")
        pieces.append(verification.status if verification else "unverified")
        pieces.append(f"level {level}")
        return ", ".join(pieces) + "."
