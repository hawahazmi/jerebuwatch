# JerebuWatch 🌫️

Malaysia's haze monitoring dashboard — what the air is doing, why, and what to do about it.

> **Status:** Phase 0 — foundations. Public dashboard coming soon.

## What this is
A free, public air-quality dashboard for Malaysia built for the 2026 haze season (Super El Niño year). Connects current air quality → transboundary hotspots → plain-language daily guidance, in BM & EN.

## Stack
- Static frontend (ECharts + Leaflet) on Vercel
- Python data pipeline on GitHub Actions cron (daily refresh, commits JSON, auto-redeploys)
- Data: Open-Meteo Air Quality API (primary), APIMS/DOE (official readings, planned), NASA FIRMS hotspots (planned)

## Repository layout
```
index.html                  Static dashboard (dark, mobile-first)
data/latest.json            Latest air quality snapshot (auto-refreshed)
data/history/               Daily snapshots archive
scripts/fetch_air_quality.py  Data pipeline
.github/workflows/          Automated data refresh (cron)
SCOPE.md                    Full project scope & ambition assessment
```

## Data sources & license
Air quality data from Open-Meteo.com (CC BY 4.0). Historical context planned from data.gov.my open data. See `SCOPE.md` for full methodology.

## Project docs
- `SCOPE.md` — objectives, features, risks, anti-stall plan
- Timeline: 1 Sep – 24 Nov 2026, staged public launches per phase

Built by Amalin Hawa. First solo passion project. Updates as the build progresses.
