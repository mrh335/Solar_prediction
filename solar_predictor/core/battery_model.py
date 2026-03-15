"""
Battery energy storage simulation.

Models a DC-coupled or AC-coupled battery storage system with:
- Configurable capacity, charge/discharge rates, and efficiency
- State of charge (SoC) tracking
- Grid import/export calculation
- Energy balance reporting
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class BatteryState:
    soc: float          # State of charge (0-1)
    energy_kwh: float   # Energy stored (kWh)


@dataclass
class TimeStepResult:
    solar_kw: float
    load_kw: float
    battery_kw: float       # Positive = charging, negative = discharging
    grid_kw: float          # Positive = import from grid, negative = export
    soc: float              # SoC after this step
    self_consumed_kw: float # Solar used directly by loads
    curtailed_kw: float     # Solar that couldn't be used or stored


class BatteryModel:
    """
    Simulates a battery storage system for a sequence of time steps.

    Strategy: Solar-first self-consumption
      1. Solar power satisfies load directly
      2. Surplus solar charges battery (up to max rate and max SoC)
      3. Any remaining surplus is exported to grid
      4. If solar < load, battery discharges to cover deficit (up to max rate and min SoC)
      5. Any remaining deficit is imported from grid
    """

    def __init__(self, config: dict):
        bat = config["battery"]
        self.capacity_kwh = bat["capacity_kwh"]
        self.max_charge_kw = bat["max_charge_kw"]
        self.max_discharge_kw = bat["max_discharge_kw"]
        self.charge_efficiency = bat["charge_efficiency"]
        self.discharge_efficiency = bat["discharge_efficiency"]
        self.min_soc = bat["min_soc"]
        self.max_soc = bat["max_soc"]
        self.initial_soc = bat.get("initial_soc", 0.5)
        self._soc = self.initial_soc

    @property
    def soc(self) -> float:
        return self._soc

    @property
    def energy_kwh(self) -> float:
        return self._soc * self.capacity_kwh

    def reset(self, soc: Optional[float] = None):
        self._soc = soc if soc is not None else self.initial_soc

    def step(self, solar_kw: float, load_kw: float, dt_hours: float = 1.0) -> TimeStepResult:
        """
        Simulate one time step of duration dt_hours.
        Returns a TimeStepResult with power flows and new SoC.
        """
        surplus = solar_kw - load_kw
        self_consumed = min(solar_kw, load_kw)
        battery_kw = 0.0
        curtailed_kw = 0.0

        if surplus > 0:
            # Charge battery with surplus
            headroom_kwh = (self.max_soc - self._soc) * self.capacity_kwh
            max_charge_kwh = min(self.max_charge_kw * dt_hours, headroom_kwh)
            # Energy that can enter battery from grid side
            charge_kwh = min(surplus * dt_hours * self.charge_efficiency, max_charge_kwh)
            actual_charge_kw = charge_kwh / (dt_hours * self.charge_efficiency)
            battery_kw = actual_charge_kw  # positive = charging

            energy_added = charge_kwh
            self._soc = min(self.max_soc, self._soc + energy_added / self.capacity_kwh)

            exported_kw = max(0.0, surplus - actual_charge_kw)
            curtailed_kw = 0.0  # for now, always export surplus
            grid_kw = -exported_kw  # negative = export
        else:
            # Discharge battery to cover deficit
            deficit = -surplus
            available_kwh = (self._soc - self.min_soc) * self.capacity_kwh
            max_discharge_kwh = min(self.max_discharge_kw * dt_hours, available_kwh)
            # Energy that can be delivered to loads from battery
            discharge_kwh = min(deficit * dt_hours / self.discharge_efficiency, max_discharge_kwh)
            actual_discharge_kw = discharge_kwh * self.discharge_efficiency / dt_hours
            battery_kw = -actual_discharge_kw  # negative = discharging

            energy_removed = discharge_kwh
            self._soc = max(self.min_soc, self._soc - energy_removed / self.capacity_kwh)

            remaining_deficit_kw = deficit - actual_discharge_kw
            grid_kw = remaining_deficit_kw  # positive = import
            curtailed_kw = 0.0

        return TimeStepResult(
            solar_kw=solar_kw,
            load_kw=load_kw,
            battery_kw=battery_kw,
            grid_kw=grid_kw,
            soc=self._soc,
            self_consumed_kw=self_consumed,
            curtailed_kw=curtailed_kw,
        )

    def simulate_day(
        self,
        solar_kw: pd.Series,
        load_kw: pd.Series,
        initial_soc: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Simulate a full day (or any sequence of hourly steps).
        Returns a DataFrame with all power flows and SoC history.
        """
        self.reset(initial_soc)
        results = []
        for t in solar_kw.index:
            s = solar_kw.loc[t]
            l = load_kw.loc[t]
            r = self.step(s, l, dt_hours=1.0)
            results.append({
                "time": t,
                "solar_kw": r.solar_kw,
                "load_kw": r.load_kw,
                "battery_kw": r.battery_kw,
                "grid_kw": r.grid_kw,
                "soc_pct": r.soc * 100,
                "self_consumed_kw": r.self_consumed_kw,
                "curtailed_kw": r.curtailed_kw,
            })
        df = pd.DataFrame(results).set_index("time")
        return df


def summarise_day(df: pd.DataFrame) -> dict:
    """Compute daily energy summary from a simulate_day result DataFrame."""
    return {
        "solar_kwh": df["solar_kw"].clip(lower=0).sum(),
        "load_kwh": df["load_kw"].sum(),
        "grid_import_kwh": df["grid_kw"].clip(lower=0).sum(),
        "grid_export_kwh": (-df["grid_kw"].clip(upper=0)).sum(),
        "self_consumed_kwh": df["self_consumed_kw"].sum(),
        "battery_charge_kwh": df["battery_kw"].clip(lower=0).sum(),
        "battery_discharge_kwh": (-df["battery_kw"].clip(upper=0)).sum(),
        "soc_start_pct": df["soc_pct"].iloc[0],
        "soc_end_pct": df["soc_pct"].iloc[-1],
        "self_sufficiency_pct": (
            (df["self_consumed_kw"].sum() + (-df["battery_kw"].clip(upper=0)).sum())
            / max(df["load_kw"].sum(), 0.001) * 100
        ),
        "self_consumption_pct": (
            df["self_consumed_kw"].sum()
            / max(df["solar_kw"].clip(lower=0).sum(), 0.001) * 100
        ),
    }
