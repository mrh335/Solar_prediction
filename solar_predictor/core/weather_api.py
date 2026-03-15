"""
Weather data integration using the Open-Meteo API.

Open-Meteo is free, requires no API key, and provides:
  - 16-day hourly forecasts
  - Historical archive data (archive-api)
  - Variables: shortwave_radiation, direct_radiation, diffuse_radiation,
    cloud_cover, temperature_2m, windspeed_10m, precipitation

Docs: https://open-meteo.com/en/docs
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import requests

log = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARS = [
    "shortwave_radiation",      # GHI  (W/m²)
    "direct_radiation",         # DNI on horizontal  (W/m²)
    "diffuse_radiation",        # DHI  (W/m²)
    "cloud_cover",              # 0-100 %
    "temperature_2m",           # °C
    "windspeed_10m",            # m/s
    "precipitation",            # mm
]


class WeatherAPI:
    """Fetches and parses Open-Meteo weather data."""

    def __init__(self, latitude: float, longitude: float, timezone: str, cache_hours: int = 1):
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = timezone
        self._cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
        self._cache_hours = cache_hours

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        fetched_at, _ = self._cache[key]
        return (datetime.now() - fetched_at).total_seconds() < self._cache_hours * 3600

    def _fetch(self, url: str, params: dict) -> pd.DataFrame:
        log.debug("Fetching weather: %s %s", url, params)
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
        times = pd.to_datetime(hourly.pop("time"))
        df = pd.DataFrame(hourly, index=times)
        df.index = df.index.tz_localize(self.timezone, ambiguous="infer", nonexistent="shift_forward")
        df.index.name = "time"
        # Rename columns to shorter names
        rename = {
            "shortwave_radiation": "ghi",
            "direct_radiation": "direct_horizontal",
            "diffuse_radiation": "dhi",
            "cloud_cover": "cloud_cover_pct",
            "temperature_2m": "temp_c",
            "windspeed_10m": "wind_ms",
            "precipitation": "precip_mm",
        }
        df = df.rename(columns=rename)
        # Derive DNI from direct horizontal and solar geometry where possible
        # direct_radiation from OM is actually Direct Normal Irradiance on tilted at zenith
        # We approximate DNI: direct_horizontal / cos(zenith) – handled in system_sim
        df["dni"] = df.get("direct_horizontal", pd.Series(0.0, index=df.index))
        df["ghi"] = df["ghi"].clip(lower=0)
        df["dhi"] = df["dhi"].clip(lower=0)
        df["dni"] = df["dni"].clip(lower=0)
        df["temp_c"] = df["temp_c"].fillna(15.0)
        df["wind_ms"] = df["wind_ms"].fillna(1.0)
        df["cloud_cover_pct"] = df["cloud_cover_pct"].fillna(0.0)
        df["precip_mm"] = df["precip_mm"].fillna(0.0)
        return df

    def get_forecast(self, days_ahead: int = 7) -> pd.DataFrame:
        """Fetch hourly forecast for the next N days (max 16)."""
        key = f"forecast_{days_ahead}"
        if self._is_cached(key):
            return self._cache[key][1]
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": ",".join(HOURLY_VARS),
            "forecast_days": min(days_ahead, 16),
            "timezone": self.timezone,
        }
        df = self._fetch(FORECAST_URL, params)
        self._cache[key] = (datetime.now(), df)
        return df

    def get_historical(self, start: date, end: date) -> pd.DataFrame:
        """Fetch hourly historical data between start and end dates."""
        # Archive API has ~5-day lag; bridge gap with forecast if needed
        archive_end = min(end, date.today() - timedelta(days=5))
        forecast_start = max(start, date.today() - timedelta(days=4))

        frames = []
        if archive_end >= start:
            key = f"archive_{start}_{archive_end}"
            if self._is_cached(key):
                frames.append(self._cache[key][1])
            else:
                params = {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "hourly": ",".join(HOURLY_VARS),
                    "start_date": start.isoformat(),
                    "end_date": archive_end.isoformat(),
                    "timezone": self.timezone,
                }
                df = self._fetch(ARCHIVE_URL, params)
                self._cache[key] = (datetime.now(), df)
                frames.append(df)

        if forecast_start <= end and end >= date.today() - timedelta(days=4):
            try:
                fdf = self.get_forecast(days_ahead=16)
                mask = (fdf.index.date >= forecast_start) & (fdf.index.date <= end)
                frames.append(fdf[mask])
            except Exception as e:
                log.warning("Could not fetch forecast bridge: %s", e)

        if not frames:
            raise ValueError(f"No weather data available for {start} to {end}")

        result = pd.concat(frames).sort_index()
        result = result[~result.index.duplicated(keep="first")]
        return result

    def get_day(self, target_date: date) -> pd.DataFrame:
        """
        Fetch hourly weather for a single day.
        Uses historical archive for past dates, forecast for future dates.
        """
        today = date.today()
        if target_date <= today - timedelta(days=5):
            return self.get_historical(target_date, target_date)
        else:
            df = self.get_forecast(days_ahead=16)
            mask = df.index.date == target_date
            day_df = df[mask]
            if day_df.empty:
                raise ValueError(f"No forecast data available for {target_date}")
            return day_df

    def get_dni_from_geometry(
        self, ghi: pd.Series, dhi: pd.Series, solar_zenith: pd.Series
    ) -> pd.Series:
        """
        Derive DNI from GHI and DHI using the geometry relationship:
          DNI = (GHI - DHI) / cos(zenith)
        This is more accurate than using Open-Meteo's direct_radiation directly.
        """
        cos_z = pd.Series(
            pvlib_cos_zenith(solar_zenith.values), index=solar_zenith.index
        )
        # Avoid division by very small values (sun below horizon)
        cos_z = cos_z.clip(lower=0.087)  # ~85° zenith
        direct = (ghi - dhi).clip(lower=0)
        dni = direct / cos_z
        return dni.clip(lower=0, upper=1400)


def pvlib_cos_zenith(zenith_deg):
    """cos of zenith angle, clipped to avoid numerical issues."""
    import numpy as np
    return np.cos(np.radians(zenith_deg)).clip(min=0)
