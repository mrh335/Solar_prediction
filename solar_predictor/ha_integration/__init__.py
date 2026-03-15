"""
Solar Predictor - Home Assistant Custom Integration.

Installation:
    Copy the entire `ha_integration/` folder to your HA config directory as:
      <config>/custom_components/solar_predictor/

    The folder contains:
      __init__.py       (this file)
      manifest.json
      const.py
      config_flow.py
      sensor.py

Dependencies (added automatically via manifest.json):
    pvlib, pandas, pyyaml, requests
"""

import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, SCAN_INTERVAL, CONF_YAML_PATH

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Solar Predictor component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Predictor from a config entry."""
    coordinator = SolarPredictorCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class SolarPredictorCoordinator(DataUpdateCoordinator):
    """Coordinator that runs the solar simulation and exposes results to sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._entry = entry
        self._simulator = None

    def _load_simulator(self):
        """Lazy-load the simulator (imports heavy deps only when needed)."""
        if self._simulator is not None:
            return
        import yaml
        import sys
        import os

        yaml_path = self._entry.data.get(CONF_YAML_PATH, "")
        if not yaml_path or not os.path.exists(yaml_path):
            raise UpdateFailed(f"Config file not found: {yaml_path}")

        # Add the solar_predictor package to the path if needed
        pkg_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        if pkg_dir not in sys.path:
            sys.path.insert(0, pkg_dir)

        from solar_predictor.core.system_sim import SystemSimulator
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        self._simulator = SystemSimulator(config)

    async def _async_update_data(self) -> dict:
        """Fetch updated predictions. Called by the coordinator on schedule."""
        return await self.hass.async_add_executor_job(self._update_sync)

    def _update_sync(self) -> dict:
        """Synchronous update — runs in executor thread."""
        self._load_simulator()
        today = date.today()
        tomorrow = today + timedelta(days=1)
        data = {}
        for label, d in [("today", today), ("tomorrow", tomorrow)]:
            try:
                df, summary = self._simulator.simulate_day(d)
                data[label] = {
                    "summary": summary,
                    "hourly": df,
                }
            except Exception as e:
                _LOGGER.error("Failed to simulate %s: %s", label, e)
                data[label] = None
        return data
