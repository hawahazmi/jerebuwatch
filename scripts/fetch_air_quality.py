"""
JerebuWatch data pipeline — Phase 0
Fetches hourly air quality (PM10, PM2.5) for key Malaysian locations from
Open-Meteo Air Quality API (free, no key required) and writes:
  - data/latest.json        : current snapshot for the dashboard
  - data/history/YYYY-MM-DD.json : daily archive for trend building

Stdlib only (urllib) so it runs anywhere: local Windows, GitHub Actions.
AQI mapping uses the Malaysian API thresholds (DOE/APIMS):
  0-50 Good | 51-100 Moderate | 101-200 Unhealthy | 201-300 Very Unhealthy | >300 Hazardous
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

MYT = timezone(timedelta(hours=8))
BASE = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Key locations: Klang Valley haze corridor, Sarawak hot zones, plus coverage
LOCATIONS = [
    {"name": "Kuala Lumpur",  "state": "Kuala Lumpur", "lat": 3.1390, "lon": 101.6869},
    {"name": "Petaling Jaya", "state": "Selangor",     "lat": 3.1072, "lon": 101.6067},
    {"name": "Shah Alam",     "state": "Selangor",     "lat": 3.0733, "lon": 101.5180},
    {"name": "Klang",         "state": "Selangor",     "lat": 3.0367, "lon": 101.4430},
    {"name": "Kuching",       "state": "Sarawak",      "lat": 1.5535, "lon": 110.3592},
    {"name": "Sibu",          "state": "Sarawak",      "lat": 2.2873, "lon": 111.8310},
    {"name": "Johor Bahru",   "state": "Johor",        "lat": 1.4927, "lon": 103.7414},
    {"name": "Penang",        "state": "Penang",       "lat": 5.4141, "lon": 100.3288},
    {"name": "Kota Kinabalu", "state": "Sabah",        "lat": 5.9804, "lon": 116.0735},
    {"name": "Ipoh",          "state": "Perak",        "lat": 4.5975, "lon": 101.0901},
]

API_BANDS = [
    (50, "Good", "Baik", "#4caf50"),
    (100, "Moderate", "Sederhana", "#ffc107"),
    (200, "Unhealthy", "Tidak Sihat", "#ff7043"),
    (300, "Very Unhealthy", "Sangat Tidak Sihat", "#e53935"),
    (float("inf"), "Hazardous", "Berbahaya", "#8e24aa"),
]


def api_from_pm25(pm25):
    """Approximate Malaysian API value from PM2.5 (dominant haze pollutant)."""
    if pm25 is None:
        return None
    return round(pm25 * 2.0)  # coarse mapping; methodology page will document this


def classify(api_value):
    for ceiling, en, bm, color in API_BANDS:
        if api_value <= ceiling:
            return {"label_en": en, "label_bm": bm, "color": color}
    return {"label_en": "Unknown", "label_bm": "Tidak diketahui", "color": "#9e9e9e"}


def fetch_location(loc):
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "hourly": "pm10,pm2_5",
        "forecast_days": 1,
        "past_days": 7,   # 7 days back for trend context
        "timezone": "Asia/Kuala_Lumpur",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "JerebuWatch/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    pm25_series = hourly.get("pm2_5", [])
    pm10_series = hourly.get("pm10", [])

    now = datetime.now(MYT).strftime("%Y-%m-%dT%H:00")
    current_idx = times.index(now) if now in times else (len(times) - 1)

    pm25_now = pm25_series[current_idx] if current_idx < len(pm25_series) else None
    pm10_now = pm10_series[current_idx] if current_idx < len(pm10_series) else None
    api_now = api_from_pm25(pm25_now)

    return {
        **loc,
        "pm25_now": pm25_now,
        "pm10_now": pm10_now,
        "api_now": api_now,
        "status": classify(api_now) if api_now is not None else None,
        "hourly": [
            {"time": t, "pm25": pm25_series[i], "pm10": pm10_series[i]}
            for i, t in enumerate(times)
        ],
    }


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    history_dir = data_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    fetched_at = datetime.now(MYT).isoformat(timespec="seconds")
    results, errors = [], []

    for loc in LOCATIONS:
        try:
            results.append(fetch_location(loc))
            print(f"  OK  {loc['name']:15s} API={results[-1]['api_now']}")
        except Exception as exc:  # keep pipeline alive on single-location failure
            errors.append({"location": loc["name"], "error": str(exc)})
            print(f"FAIL  {loc['name']:15s} {exc}", file=sys.stderr)

    snapshot = {
        "generated_at": fetched_at,
        "source": "Open-Meteo Air Quality API (modelled; APIMS official readings planned)",
        "locations": results,
        "errors": errors,
    }

    latest_path = data_dir / "latest.json"
    today_path = history_dir / f"{datetime.now(MYT).strftime('%Y-%m-%d')}.json"
    for path in (latest_path, today_path):
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nWrote {latest_path} and {today_path}")
    print(f"{len(results)}/{len(LOCATIONS)} locations fetched, {len(errors)} errors")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
