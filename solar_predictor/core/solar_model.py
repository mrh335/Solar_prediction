"""
Solar irradiance and power production model using pvlib.

Calculates:
- Sun position (azimuth, elevation) for any location and time
- Clear-sky irradiance (GHI, DNI, DHI)
- Plane-of-array (POA) irradiance for tilted, oriented array
- Cell temperature corrections
- DC and AC power output
"""

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location


# Residential load profile: 24 multipliers relative to hourly mean.
# Shaped as a typical UK/EU household (morning peak, evening peak).
DEFAULT_LOAD_PROFILE = np.array([
    0.30, 0.22, 0.18, 0.18, 0.20, 0.35,  # 00-05
    0.60, 0.95, 1.05, 0.85, 0.70, 0.68,  # 06-11
    0.75, 0.68, 0.60, 0.65, 0.80, 1.15,  # 12-17
    1.50, 1.45, 1.30, 1.10, 0.80, 0.50,  # 18-23
])


class SolarModel:
    """Computes solar power output for a PV array at a given location."""

    def __init__(self, config: dict):
        self.config = config
        loc_cfg = config["location"]
        self.location = Location(
            latitude=loc_cfg["latitude"],
            longitude=loc_cfg["longitude"],
            tz=loc_cfg["timezone"],
            altitude=loc_cfg.get("altitude", 0),
            name=config.get("system", {}).get("name", "Solar System"),
        )
        arr = config["array"]
        self.tilt = arr["tilt"]
        self.azimuth = arr["azimuth"]
        panel = arr["panels"]
        self.panel_count = panel["count"]
        self.panel_watts_stc = panel["watts_stc"]
        self.panel_efficiency = panel["efficiency"]
        self.temp_coefficient = panel["temp_coefficient"]   # per °C, negative
        self.noct = panel["noct"]
        self.array_losses = arr.get("losses", 0.05)
        self.inverter_efficiency = config["inverter"]["efficiency"]
        self.inverter_max_kw = config["inverter"]["max_power_kw"]
        # Total STC DC rating
        self.system_kwp = self.panel_count * self.panel_watts_stc / 1000.0

    def get_solar_position(self, times: pd.DatetimeIndex) -> pd.DataFrame:
        """Return solar position DataFrame (apparent_zenith, azimuth, elevation…)."""
        return self.location.get_solarposition(times)

    def get_clearsky(self, times: pd.DatetimeIndex) -> pd.DataFrame:
        """Return clear-sky GHI, DNI, DHI using Ineichen model."""
        return self.location.get_clearsky(times, model="ineichen")

    def irradiance_on_array(
        self,
        times: pd.DatetimeIndex,
        ghi: pd.Series,
        dni: pd.Series,
        dhi: pd.Series,
    ) -> pd.Series:
        """
        Calculate plane-of-array (POA) global irradiance for the tilted surface.

        Uses the Hay-Davies-Klucher-Reindl (HDKR) transposition model.
        Returns a Series of POA irradiance in W/m².
        """
        solpos = self.location.get_solarposition(times)
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=self.tilt,
            surface_azimuth=self.azimuth,
            solar_zenith=solpos["apparent_zenith"],
            solar_azimuth=solpos["azimuth"],
            dni=dni,
            ghi=ghi,
            dhi=dhi,
            model="haydavies",
        )
        poa_global = poa["poa_global"].fillna(0).clip(lower=0)
        return poa_global

    def cell_temperature(
        self,
        poa_irradiance: pd.Series,
        ambient_temp: pd.Series,
        wind_speed: pd.Series | None = None,
    ) -> pd.Series:
        """
        Estimate cell temperature using the Faiman model.

        NOCT-based simplified formula when wind is unavailable:
          T_cell = T_ambient + (NOCT - 20) / 800 * G_poa
        """
        if wind_speed is None:
            wind_speed = pd.Series(1.0, index=poa_irradiance.index)
        # Use pvlib Faiman model (requires wind speed)
        try:
            t_cell = pvlib.temperature.faiman(
                poa_irradiance, ambient_temp, wind_speed
            )
        except Exception:
            # Fallback NOCT model
            t_cell = ambient_temp + (self.noct - 20.0) / 800.0 * poa_irradiance
        return t_cell

    def dc_power_kw(
        self,
        poa_irradiance: pd.Series,
        cell_temp: pd.Series,
    ) -> pd.Series:
        """
        Compute DC power output in kW.

        P_dc = (G_poa / 1000) * P_stc_kWp * η_temp * (1 - losses)
        η_temp = 1 + temp_coeff * (T_cell - 25)
        """
        g_fraction = poa_irradiance / 1000.0
        eta_temp = 1.0 + self.temp_coefficient * (cell_temp - 25.0)
        eta_temp = eta_temp.clip(lower=0.5)  # safety floor
        p_dc = g_fraction * self.system_kwp * eta_temp * (1.0 - self.array_losses)
        return p_dc.clip(lower=0)

    def ac_power_kw(self, p_dc: pd.Series) -> pd.Series:
        """Convert DC power to AC, clamped by inverter limits."""
        p_ac = p_dc * self.inverter_efficiency
        return p_ac.clip(upper=self.inverter_max_kw, lower=0)

    def simulate_production(
        self,
        times: pd.DatetimeIndex,
        ghi: pd.Series,
        dni: pd.Series,
        dhi: pd.Series,
        ambient_temp: pd.Series,
        wind_speed: pd.Series | None = None,
        calibration_factor: float = 1.0,
    ) -> pd.Series:
        """
        Full pipeline: irradiance → cell temp → DC → AC power (kW).
        Returns AC power output in kW at each time step.
        """
        poa = self.irradiance_on_array(times, ghi, dni, dhi)
        t_cell = self.cell_temperature(poa, ambient_temp, wind_speed)
        p_dc = self.dc_power_kw(poa, t_cell)
        p_ac = self.ac_power_kw(p_dc)
        return (p_ac * calibration_factor).rename("production_kw")

    def build_load_profile(self, annual_kwh: float, custom_profile=None) -> np.ndarray:
        """
        Build a 24-element hourly load profile (kW for each hour of day).
        Uses custom profile if provided, otherwise scales the default shape.
        """
        if custom_profile is not None:
            profile = np.array(custom_profile, dtype=float)
        else:
            profile = DEFAULT_LOAD_PROFILE.copy()
        # Normalise so the total equals daily average energy
        daily_kwh = annual_kwh / 365.0
        profile = profile / profile.sum() * daily_kwh
        return profile  # kWh per hour (= kW average for that hour)

    def sun_elevation_series(self, times: pd.DatetimeIndex) -> pd.Series:
        """Return sun elevation angle (degrees above horizon) series."""
        solpos = self.location.get_solarposition(times)
        elevation = solpos["apparent_elevation"].clip(lower=0)
        return elevation.rename("sun_elevation_deg")

    def sun_azimuth_series(self, times: pd.DatetimeIndex) -> pd.Series:
        """Return sun azimuth angle (degrees) series."""
        solpos = self.location.get_solarposition(times)
        return solpos["azimuth"].rename("sun_azimuth_deg")
