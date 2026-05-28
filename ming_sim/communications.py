"""Court dispatch and travel-time helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Tuple

from ming_sim.assets import load_json_asset, require_dict
from ming_sim.locations import COURT_LOCATION


CHANNEL_BY_KIND = {
    "letter": "letter_days",
    "letter_reply": "letter_days",
    "decree": "decree_days",
    "secret_order": "secret_days",
}


@lru_cache(maxsize=1)
def travel_times() -> Dict[str, Dict[str, int]]:
    raw = require_dict(load_json_asset("travel_times.json"), "travel_times.json")
    regions = require_dict(raw.get("regions"), "travel_times.json.regions")
    out: Dict[str, Dict[str, int]] = {}
    for region_id, item in regions.items():
        data = require_dict(item, f"travel_times.json.regions.{region_id}")
        out[str(region_id)] = {
            "letter_days": int(data.get("letter_days") or 0),
            "decree_days": int(data.get("decree_days") or 0),
            "secret_days": int(data.get("secret_days") or 0),
        }
    return out


def communication_days(origin: str, destination: str, kind: str = "letter") -> int:
    origin = (origin or COURT_LOCATION).strip()
    destination = (destination or COURT_LOCATION).strip()
    if origin == destination:
        return 0
    channel = CHANNEL_BY_KIND.get(kind, "letter_days")
    times = travel_times()

    def _one_side(region_id: str) -> int:
        data = times.get(region_id) or {}
        if channel in data:
            return max(0, int(data[channel]))
        default = times.get("__default__", {})
        return max(1, int(default.get(channel) or default.get("letter_days") or 3))

    if origin == COURT_LOCATION:
        return _one_side(destination)
    if destination == COURT_LOCATION:
        return _one_side(origin)
    return _one_side(origin) + _one_side(destination)


def date_after_days(year: int, period: int, day: int, days: int) -> Tuple[int, int, int]:
    y, m, d = int(year), int(period), int(day) + max(0, int(days))
    while d > 30:
        d -= 30
        m += 1
        if m > 12:
            m = 1
            y += 1
    return y, m, d
