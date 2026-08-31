"""
JerebuWatch data pipeline — Phase 0/1
Fetches hourly air quality (PM10, PM2.5) for key Malaysian locations from
Open-Meteo Air Quality API (free, no key required) and writes:
  - data/latest.json        : current snapshot + last 24h (dashboard map)
  - data/trends.json        : 30-day hourly series (drill-down charts)
  - data/history/YYYY-MM-DD.json : daily archive of the current snapshot

Stdlib only (urllib) so it runs anywhere: local Windows, GitHub Actions.
AQI calculation: piecewise-linear conversion of PM2.5 using the US-AQI/PSI
breakpoints that Malaysian API is derived from (documented in methodology).
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

# US-AQI / PSI PM2.5 breakpoints: (conc_lo, conc_hi, aqi_lo, aqi_hi)
# Malaysian API is PSI-derived; this is the standard defensible conversion.
PM25_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def api_from_pm25(pm25):
    """Convert PM2.5 (µg/m³) to an API-equivalent value via AQI breakpoints."""
    if pm25 is None:
        return None
    if pm25 <= 0:
        return 0
    if pm25 > 500.4:
        return 500
    for clo, chi, alo, ahi in PM25_BREAKPOINTS:
        if clo <= pm25 <= chi:
            return round(alo + (ahi - alo) * (pm25 - clo) / (chi - clo))
    return 500


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
        "past_days": 30,  # 30 days back for trend charts
        "timezone": "Asia/Kuala_Lumpur",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "JerebuWatch/0.2"})
    with urllib.request.urlopen(req, timeout=45) as resp:
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

    # Rolling averages for trend narrative (last 24h vs previous 30 days)
    valid_30d = [v for v in pm25_series[: current_idx + 1] if v is not None]
    last24 = valid_30d[-24:]
    before = valid_30d[:-24] if len(valid_30d) > 24 else []
    avg_last24 = round(sum(last24) / len(last24), 1) if last24 else None
    avg_30d = round(sum(valid_30d) / len(valid_30d), 1) if valid_30d else None

    # Full series with per-hour API for trends.json
    full_series = [
        {
            "time": t,
            "pm25": pm25_series[i],
            "pm10": pm10_series[i],
            "api": api_from_pm25(pm25_series[i]),
        }
        for i, t in enumerate(times)
    ]

    return {
        **loc,
        "pm25_now": pm25_now,
        "pm10_now": pm10_now,
        "api_now": api_now,
        "status": classify(api_now) if api_now is not None else None,
        "pm25_avg_last24h": avg_last24,
        "pm25_avg_30d": avg_30d,
        # last 24h for map popups; full 30d goes to trends.json separately
        "hourly": [r for r in full_series if r["time"] >= times[max(current_idx - 23, 0)]],
        "series_30d": full_series,
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

    # Slim trends file for drill-down charts (no duplicates of latest.json fields)
    trends = {
        "generated_at": fetched_at,
        "locations": [
            {
                "name": r["name"],
                "state": r["state"],
                "series": [
                    {"t": p["time"], "api": p["api"], "pm25": p["pm25"], "pm10": p["pm10"]}
                    for p in r["series_30d"]
                ],
            }
            for r in results
        ],
    }

    latest_path = data_dir / "latest.json"
    trends_path = data_dir / "trends.json"
    today_path = history_dir / f"{datetime.now(MYT).strftime('%Y-%m-%d')}.json"
    latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    trends_path.write_text(json.dumps(trends, ensure_ascii=False), encoding="utf-8")
    today_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nWrote {latest_path.name}, {trends_path.name}, {today_path.name}")
    print(f"{len(results)}/{len(LOCATIONS)} locations fetched, {len(errors)} errors")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
