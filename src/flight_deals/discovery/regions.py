from __future__ import annotations

NORTH_AMERICA_REGIONS = {
    "canada_nearby_us",
    "united_states",
    "mexico_caribbean_central_america",
}

OUTSIDE_NORTH_AMERICA_REGIONS = {
    "south_america",
    "europe",
    "middle_east_africa",
    "asia",
    "oceania",
}

SERPAPI_AREA_BY_REGION = {
    # SerpApi documents /m/02j9z as Europe for google_travel_explore arrival_area_id.
    "europe": "/m/02j9z",
    # Wikidata Freebase ID for South America.
    "south_america": "/m/06n3y",
}

DESTINATION_REGION_BY_CODE = {
    "AMS": "europe",
    "ATH": "europe",
    "BCN": "europe",
    "CDG": "europe",
    "CPH": "europe",
    "DUB": "europe",
    "FCO": "europe",
    "FRA": "europe",
    "IST": "middle_east_africa",
    "LHR": "europe",
    "LIS": "europe",
    "MAD": "europe",
    "MXP": "europe",
    "ORY": "europe",
    "OSL": "europe",
    "VIE": "europe",
    "ZRH": "europe",
    "BOG": "south_america",
    "EZE": "south_america",
    "GIG": "south_america",
    "GRU": "south_america",
    "LIM": "south_america",
    "SCL": "south_america",
    "TLV": "middle_east_africa",
    "CAI": "middle_east_africa",
    "CPT": "middle_east_africa",
    "DXB": "middle_east_africa",
    "JNB": "middle_east_africa",
    "AUH": "middle_east_africa",
    "BKK": "asia",
    "DEL": "asia",
    "HKG": "asia",
    "ICN": "asia",
    "NRT": "asia",
    "HND": "asia",
    "SIN": "asia",
    "TPE": "asia",
    "MEL": "oceania",
    "AKL": "oceania",
    "SYD": "oceania",
    "YYC": "canada_nearby_us",
    "YVR": "canada_nearby_us",
    "YUL": "canada_nearby_us",
    "LAX": "united_states",
    "MIA": "united_states",
    "NYC": "united_states",
    "SAN": "united_states",
    "SFO": "united_states",
    "CUN": "mexico_caribbean_central_america",
    "MEX": "mexico_caribbean_central_america",
    "PUJ": "mexico_caribbean_central_america",
}

COUNTRY_REGION_BY_NAME = {
    "ireland": "europe",
    "united kingdom": "europe",
    "england": "europe",
    "scotland": "europe",
    "france": "europe",
    "spain": "europe",
    "portugal": "europe",
    "italy": "europe",
    "germany": "europe",
    "netherlands": "europe",
    "belgium": "europe",
    "switzerland": "europe",
    "austria": "europe",
    "greece": "europe",
    "denmark": "europe",
    "norway": "europe",
    "sweden": "europe",
    "finland": "europe",
    "iceland": "europe",
    "poland": "europe",
    "czechia": "europe",
    "czech republic": "europe",
    "hungary": "europe",
    "turkey": "middle_east_africa",
    "israel": "middle_east_africa",
    "united arab emirates": "middle_east_africa",
    "qatar": "middle_east_africa",
    "egypt": "middle_east_africa",
    "morocco": "middle_east_africa",
    "south africa": "middle_east_africa",
    "kenya": "middle_east_africa",
    "colombia": "south_america",
    "peru": "south_america",
    "brazil": "south_america",
    "argentina": "south_america",
    "chile": "south_america",
    "ecuador": "south_america",
    "japan": "asia",
    "south korea": "asia",
    "china": "asia",
    "taiwan": "asia",
    "hong kong": "asia",
    "singapore": "asia",
    "thailand": "asia",
    "india": "asia",
    "vietnam": "asia",
    "philippines": "asia",
    "indonesia": "asia",
    "australia": "oceania",
    "new zealand": "oceania",
    "canada": "canada_nearby_us",
    "united states": "united_states",
    "usa": "united_states",
    "mexico": "mexico_caribbean_central_america",
    "dominican republic": "mexico_caribbean_central_america",
    "jamaica": "mexico_caribbean_central_america",
    "costa rica": "mexico_caribbean_central_america",
    "panama": "mexico_caribbean_central_america",
}


def expand_region_filter(region: str | None) -> set[str] | None:
    if not region:
        return None
    normalized = region.lower().replace("-", "_")
    if normalized in {"outside_na", "outside_north_america", "international"}:
        return set(OUTSIDE_NORTH_AMERICA_REGIONS)
    if normalized in {"north_america", "na"}:
        return set(NORTH_AMERICA_REGIONS)
    return {normalized}


def infer_destination_region(code: str, fallback: str = "unknown") -> str:
    return DESTINATION_REGION_BY_CODE.get(code.upper(), fallback)


def infer_region_from_text(*values: str | None, fallback: str = "unknown") -> str:
    haystack = " ".join(value or "" for value in values).lower()
    for country, region in COUNTRY_REGION_BY_NAME.items():
        if country in haystack:
            return region
    return fallback
