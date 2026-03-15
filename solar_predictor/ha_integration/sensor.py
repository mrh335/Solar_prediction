"""
Home Assistant sensor platform for Solar Predictor.

Exposes the following sensors:
  - sensor.solar_predictor_production_today          (kWh)
  - sensor.solar_predictor_production_tomorrow       (kWh)
  - sensor.solar_predictor_current_hour_power        (kW)
  - sensor.solar_predictor_load_today                (kWh)
  - sensor.solar_predictor_battery_soc_end_of_day    (%)
  - sensor.solar_predictor_grid_import_today         (kWh)
  - sensor.solar_predictor_grid_export_today         (kWh)
  - sensor.solar_predictor_self_sufficiency_today    (%)
  - sensor.solar_predictor_self_consumption_today    (%)
  - sensor.solar_predictor_production_tomorrow_peak  (kW)
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, "Solar Predictor")

    sensors = [
        SolarPredictorSensor(coordinator, entry, name, "production_today",
                             "Production Today", UnitOfEnergy.KILO_WATT_HOUR,
                             SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
                             "today", "solar_kwh", "mdi:solar-panel"),
        SolarPredictorSensor(coordinator, entry, name, "production_tomorrow",
                             "Production Tomorrow", UnitOfEnergy.KILO_WATT_HOUR,
                             SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT,
                             "tomorrow", "solar_kwh", "mdi:solar-panel-large"),
        SolarPredictorSensor(coordinator, entry, name, "load_today",
                             "Load Today", UnitOfEnergy.KILO_WATT_HOUR,
                             SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
                             "today", "load_kwh", "mdi:home-lightning-bolt"),
        SolarPredictorSensor(coordinator, entry, name, "grid_import_today",
                             "Grid Import Today", UnitOfEnergy.KILO_WATT_HOUR,
                             SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
                             "today", "grid_import_kwh", "mdi:transmission-tower-import"),
        SolarPredictorSensor(coordinator, entry, name, "grid_export_today",
                             "Grid Export Today", UnitOfEnergy.KILO_WATT_HOUR,
                             SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING,
                             "today", "grid_export_kwh", "mdi:transmission-tower-export"),
        SolarPredictorSensor(coordinator, entry, name, "battery_soc_end_of_day",
                             "Battery SoC End of Day", PERCENTAGE,
                             SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT,
                             "today", "soc_end_pct", "mdi:battery-charging"),
        SolarPredictorSensor(coordinator, entry, name, "self_sufficiency_today",
                             "Self Sufficiency Today", PERCENTAGE,
                             None, SensorStateClass.MEASUREMENT,
                             "today", "self_sufficiency_pct", "mdi:leaf"),
        SolarPredictorSensor(coordinator, entry, name, "self_consumption_today",
                             "Self Consumption Today", PERCENTAGE,
                             None, SensorStateClass.MEASUREMENT,
                             "today", "self_consumption_pct", "mdi:recycle"),
        CurrentHourPowerSensor(coordinator, entry, name),
        TomorrowPeakSensor(coordinator, entry, name),
    ]

    async_add_entities(sensors)


class SolarPredictorSensor(CoordinatorEntity, SensorEntity):
    """A sensor that reads a value from the daily summary dict."""

    def __init__(self, coordinator, entry, base_name, uid_suffix, friendly_name,
                 unit, device_class, state_class, day_key, summary_key, icon):
        super().__init__(coordinator)
        self._entry = entry
        self._day_key = day_key
        self._summary_key = summary_key
        self._attr_name = f"{base_name} {friendly_name}"
        self._attr_unique_id = f"{entry.entry_id}_{uid_suffix}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or self._day_key not in data or data[self._day_key] is None:
            return None
        summary = data[self._day_key].get("summary", {})
        val = summary.get(self._summary_key)
        if val is None:
            return None
        return round(float(val), 2)


class CurrentHourPowerSensor(CoordinatorEntity, SensorEntity):
    """Reports the predicted solar power for the current hour."""

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator)
        self._attr_name = f"{base_name} Current Hour Production"
        self._attr_unique_id = f"{entry.entry_id}_current_hour_power"
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:solar-power"

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or "today" not in data or data["today"] is None:
            return None
        hourly = data["today"].get("hourly")
        if hourly is None or hourly.empty:
            return None
        now = datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        tz_aware = hourly.index.tz_convert(None)
        mask = tz_aware.hour == current_hour.hour
        if not mask.any():
            return None
        val = hourly.loc[mask, "solar_kw"].mean()
        return round(float(val), 3)


class TomorrowPeakSensor(CoordinatorEntity, SensorEntity):
    """Reports the predicted peak solar power for tomorrow."""

    def __init__(self, coordinator, entry, base_name):
        super().__init__(coordinator)
        self._attr_name = f"{base_name} Tomorrow Peak Power"
        self._attr_unique_id = f"{entry.entry_id}_tomorrow_peak"
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:solar-power-variant"

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or "tomorrow" not in data or data["tomorrow"] is None:
            return None
        hourly = data["tomorrow"].get("hourly")
        if hourly is None or hourly.empty:
            return None
        peak = hourly["solar_kw"].max()
        return round(float(peak), 3)
