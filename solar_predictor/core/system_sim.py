"""
Full system simulation orchestrator.

Ties together the weather API, solar model, and battery model to produce
complete hourly predictions for a given day or date range.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pvlib

from .solar_model import SolarModel
from .battery_model import BatteryModel, summarise_day
from .weather_api import WeatherAPI, pvlib_cos_zenith

log = logging.getLogger(__name__)


class SystemSimulator:
    """
    Orchestrates a full-day simulation for a solar + battery system.

    Workflow for a given date:
      1. Fetch hourly weather from Open-Meteo
      2. Compute sun position
      3. Derive proper DNI from GHI/DHI/zenith geometry
      4. Calculate POA irradiance on the tilted array
      5. Calculate cell temperature
      6. Calculate AC production
      7. Build load profile
      8. Run battery simulation
      9. Return result DataFrame + summary dict
    """

    def __init__(self, config: dict):
        self.config = config
        self.solar = SolarModel(config)
        self.battery = BatteryModel(config)
        loc = config["location"]
        self.weather = WeatherAPI(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            timezone=loc["timezone"],
            cache_hours=config.get("weather", {}).get("cache_hours", 1),
        )
        cal = config.get("calibration", {})
        self.production_factor = cal.get("production_factor", 1.0)
        self.consumption_factor = cal.get("consumption_factor", 1.0)

    def simulate_day(
        self,
        target_date: date,
        initial_soc: Optional[float] = None,
    ) -> tuple[pd.DataFrame, dict]:
        """
        Run a full-day simulation for target_date.

        Returns:
            (df, summary) where df has hourly rows and summary has daily totals.
        """
        # --- 1. Weather ---
        try:
            weather_df = self.weather.get_day(target_date)
        except Exception as e:
            log.warning("Weather fetch failed, using clear-sky fallback: %s", e)
            weather_df = self._clearsky_weather(target_date)

        # Ensure hourly index covering 24 h
        times = weather_df.index
        if len(times) == 0:
            raise ValueError(f"No weather data for {target_date}")

        # --- 2. Solar position ---
        solpos = self.solar.location.get_solarposition(times)

        # --- 3. Derive DNI from GHI and DHI ---
        ghi = weather_df["ghi"]
        dhi = weather_df["dhi"]
        cos_z = pd.Series(pvlib_cos_zenith(solpos["apparent_zenith"].values), index=times)
        cos_z_safe = cos_z.clip(lower=0.087)
        direct_horizontal = (ghi - dhi).clip(lower=0)
        dni = (direct_horizontal / cos_z_safe).clip(lower=0, upper=1400)
        # Zero out when sun is below horizon
        sun_up = solpos["apparent_elevation"] > 0
        dni = dni.where(sun_up, 0.0)
        ghi = ghi.where(sun_up, 0.0)
        dhi = dhi.where(sun_up, 0.0)

        # --- 4-6. Production ---
        ambient_temp = weather_df["temp_c"]
        wind_speed = weather_df["wind_ms"]
        production_kw = self.solar.simulate_production(
            times, ghi, dni, dhi, ambient_temp, wind_speed,
            calibration_factor=self.production_factor,
        )

        # --- 7. Load profile ---
        load_cfg = self.config.get("load", {})
        load_profile = self.solar.build_load_profile(
            annual_kwh=load_cfg.get("annual_kwh", 4500),
            custom_profile=load_cfg.get("custom_hourly_profile"),
        )
        # Map profile values to the times index
        load_kw = pd.Series(
            [load_profile[t.hour] for t in times],
            index=times,
            name="load_kw",
        ) * self.consumption_factor

        # --- 8. Battery simulation ---
        if initial_soc is None:
            initial_soc = self.config["battery"].get("initial_soc", 0.5)
        result_df = self.battery.simulate_day(production_kw, load_kw, initial_soc)

        # --- 9. Enrich with weather and sun position ---
        result_df["cloud_cover_pct"] = weather_df["cloud_cover_pct"].values
        result_df["temp_c"] = ambient_temp.values
        result_df["sun_elevation_deg"] = solpos["apparent_elevation"].clip(lower=0).values
        result_df["sun_azimuth_deg"] = solpos["azimuth"].values
        result_df["ghi"] = ghi.values
        result_df["dni"] = dni.values
        result_df["dhi"] = dhi.values

        summary = summarise_day(result_df)
        summary["date"] = target_date
        summary["system_kwp"] = self.solar.system_kwp

        return result_df, summary

    def simulate_range(
        self,
        start: date,
        end: date,
        carry_soc: bool = True,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Simulate a range of days.

        Args:
            start, end: inclusive date range
            carry_soc: if True, carry end-of-day SoC into next day

        Returns:
            (hourly_df, daily_summary_df)
        """
        soc = self.config["battery"].get("initial_soc", 0.5)
        all_hourly = []
        summaries = []
        current = start
        while current <= end:
            try:
                df, summary = self.simulate_day(current, initial_soc=soc)
                all_hourly.append(df)
                summaries.append(summary)
                if carry_soc:
                    soc = df["soc_pct"].iloc[-1] / 100.0
            except Exception as e:
                log.error("Failed to simulate %s: %s", current, e)
            current += timedelta(days=1)

        hourly_df = pd.concat(all_hourly) if all_hourly else pd.DataFrame()
        daily_df = pd.DataFrame(summaries).set_index("date") if summaries else pd.DataFrame()
        return hourly_df, daily_df

    def _clearsky_weather(self, target_date: date) -> pd.DataFrame:
        """Fallback: generate clear-sky weather data (no cloud cover)."""
        import pytz
        tz = pytz.timezone(self.config["location"]["timezone"])
        times = pd.date_range(
            start=f"{target_date} 00:00",
            periods=24,
            freq="h",
            tz=tz,
        )
        clearsky = self.solar.location.get_clearsky(times, model="ineichen")
        df = pd.DataFrame({
            "ghi": clearsky["ghi"],
            "dhi": clearsky["dhi"],
            "dni": clearsky["dni"],
            "cloud_cover_pct": 0.0,
            "temp_c": 15.0,
            "wind_ms": 1.5,
            "precip_mm": 0.0,
        }, index=times)
        return df
