"""
Calibration module: import real measured data and derive correction factors.

Supports CSV files in common formats:
  - Timestamp column + production/consumption columns
  - Auto-detects column names for common inverter/HA export formats
  - Computes multiplicative correction factors by comparing real vs modelled data
  - Optional scipy curve fitting for advanced calibration
"""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Common column name variations for auto-detection
PRODUCTION_ALIASES = [
    "production", "solar", "pv", "generated", "generation",
    "solar_kw", "pv_kw", "solar_power", "pv_power",
    "solar_kwh", "pv_kwh", "energy_produced", "yield",
    "p_ac", "p_dc", "power_w", "power_kw",
]
CONSUMPTION_ALIASES = [
    "consumption", "load", "demand", "usage", "house_load",
    "load_kw", "consumption_kw", "energy_consumed",
    "total_load", "home_consumption",
]
TIMESTAMP_ALIASES = [
    "time", "timestamp", "datetime", "date", "date_time",
    "local_time", "period_start", "period_end",
]


def load_csv(filepath: str | Path) -> pd.DataFrame:
    """
    Load and parse a CSV file containing real solar/consumption data.

    Attempts to auto-detect the timestamp column and power/energy columns.
    Returns a DataFrame with a DatetimeIndex and columns: production_kw, consumption_kw (where available).
    Power in kW; if data appears to be in W or Wh it is converted.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # --- Detect timestamp column ---
    time_col = None
    for alias in TIMESTAMP_ALIASES:
        if alias in df.columns:
            time_col = alias
            break
    if time_col is None:
        # Try the first column that can be parsed as datetime
        for col in df.columns:
            try:
                pd.to_datetime(df[col].iloc[:5])
                time_col = col
                break
            except Exception:
                continue
    if time_col is None:
        raise ValueError("Could not find a timestamp column in the CSV file.")

    df[time_col] = pd.to_datetime(df[time_col], infer_datetime_format=True)
    df = df.set_index(time_col).sort_index()
    if df.index.tz is None:
        log.warning("CSV timestamps have no timezone info; assuming UTC.")
        df.index = df.index.tz_localize("UTC")

    result = pd.DataFrame(index=df.index)

    # --- Detect production column ---
    prod_col = _find_column(df.columns, PRODUCTION_ALIASES)
    if prod_col:
        values = pd.to_numeric(df[prod_col], errors="coerce").fillna(0)
        result["production_kw"] = _to_kw(values, prod_col)
        log.info("Detected production column: '%s'", prod_col)

    # --- Detect consumption column ---
    cons_col = _find_column(df.columns, CONSUMPTION_ALIASES)
    if cons_col:
        values = pd.to_numeric(df[cons_col], errors="coerce").fillna(0)
        result["consumption_kw"] = _to_kw(values, cons_col)
        log.info("Detected consumption column: '%s'", cons_col)

    if result.empty or (prod_col is None and cons_col is None):
        raise ValueError(
            "Could not detect production or consumption columns.\n"
            f"Available columns: {list(df.columns)}"
        )

    return result


def _find_column(columns, aliases) -> Optional[str]:
    """Find the first column name that matches any alias (substring match)."""
    for alias in aliases:
        for col in columns:
            if alias in col:
                return col
    return None


def _to_kw(series: pd.Series, col_name: str) -> pd.Series:
    """
    Convert series to kW if it appears to be in W or Wh.
    Heuristic: if median non-zero value > 500, assume W (or Wh per 5-min).
    """
    median = series[series > 0].median()
    if pd.isna(median):
        return series
    if "wh" in col_name or median > 50000:
        # Wh → kWh (for energy) - leave as-is for per-period energy
        return series / 1000.0
    elif median > 500:
        # Likely in W, convert to kW
        log.info("Auto-converting column '%s' from W to kW (median=%.0f)", col_name, median)
        return series / 1000.0
    return series


class Calibrator:
    """
    Compares real measured data against model predictions to derive correction factors.
    """

    def __init__(self, simulator):
        """
        Args:
            simulator: SystemSimulator instance
        """
        self.simulator = simulator

    def compute_factors(
        self,
        real_df: pd.DataFrame,
        days_to_use: Optional[int] = None,
    ) -> dict:
        """
        Compare real production/consumption data against model predictions.

        Args:
            real_df: Output from load_csv() with production_kw and/or consumption_kw
            days_to_use: Limit to the most recent N days of data

        Returns:
            dict with production_factor, consumption_factor, statistics
        """
        # Get unique dates in the real data
        dates = sorted(set(real_df.index.date))
        if days_to_use:
            dates = dates[-days_to_use:]

        log.info("Calibrating over %d days", len(dates))

        prod_ratios = []
        cons_ratios = []

        for d in dates:
            day_real = real_df[real_df.index.date == d]
            # Resample to hourly if needed
            if len(day_real) > 30:
                day_real = day_real.resample("h").mean()

            try:
                sim_df, _ = self.simulator.simulate_day(d)
            except Exception as e:
                log.warning("Skipping %s (simulation failed): %s", d, e)
                continue

            sim_df.index = sim_df.index.tz_convert(day_real.index.tz)

            if "production_kw" in day_real.columns:
                real_prod = day_real["production_kw"].reindex(sim_df.index, method="nearest")
                sim_prod = sim_df["solar_kw"]
                valid = (real_prod > 0.05) & (sim_prod > 0.05)
                if valid.sum() > 3:
                    ratio = (real_prod[valid].sum() / sim_prod[valid].sum())
                    prod_ratios.append(ratio)

            if "consumption_kw" in day_real.columns:
                real_cons = day_real["consumption_kw"].reindex(sim_df.index, method="nearest")
                sim_cons = sim_df["load_kw"]
                valid = (real_cons > 0.05) & (sim_cons > 0.05)
                if valid.sum() > 3:
                    ratio = (real_cons[valid].sum() / sim_cons[valid].sum())
                    cons_ratios.append(ratio)

        result = {}
        if prod_ratios:
            result["production_factor"] = float(np.median(prod_ratios))
            result["production_factor_std"] = float(np.std(prod_ratios))
            result["production_factor_n"] = len(prod_ratios)
        else:
            result["production_factor"] = 1.0
            result["production_factor_std"] = 0.0
            result["production_factor_n"] = 0

        if cons_ratios:
            result["consumption_factor"] = float(np.median(cons_ratios))
            result["consumption_factor_std"] = float(np.std(cons_ratios))
            result["consumption_factor_n"] = len(cons_ratios)
        else:
            result["consumption_factor"] = 1.0
            result["consumption_factor_std"] = 0.0
            result["consumption_factor_n"] = 0

        log.info(
            "Calibration result: production_factor=%.3f (n=%d), consumption_factor=%.3f (n=%d)",
            result["production_factor"], result["production_factor_n"],
            result["consumption_factor"], result["consumption_factor_n"],
        )
        return result

    def compare_day(self, target_date: date, real_df: pd.DataFrame) -> pd.DataFrame:
        """
        Produce a comparison DataFrame for a single day: real vs predicted.
        Useful for visualising calibration accuracy.
        """
        sim_df, _ = self.simulator.simulate_day(target_date)
        day_real = real_df[real_df.index.date == target_date].copy()
        if len(day_real) > 30:
            day_real = day_real.resample("h").mean()
        day_real.index = day_real.index.tz_convert(sim_df.index.tz)
        comparison = sim_df[["solar_kw", "load_kw"]].copy()
        comparison.columns = ["predicted_production_kw", "predicted_load_kw"]
        if "production_kw" in day_real.columns:
            comparison["real_production_kw"] = day_real["production_kw"].reindex(
                comparison.index, method="nearest"
            )
        if "consumption_kw" in day_real.columns:
            comparison["real_consumption_kw"] = day_real["consumption_kw"].reindex(
                comparison.index, method="nearest"
            )
        return comparison
