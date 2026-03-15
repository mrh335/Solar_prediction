"""Constants for the Solar Predictor integration."""

from datetime import timedelta

DOMAIN = "solar_predictor"
SCAN_INTERVAL = timedelta(hours=1)

CONF_YAML_PATH = "yaml_path"
CONF_NAME = "name"

# Sensor unique ID suffixes
SENSOR_SOLAR_TODAY = "solar_production_today"
SENSOR_SOLAR_TOMORROW = "solar_production_tomorrow"
SENSOR_SOLAR_NOW = "solar_production_current_hour"
SENSOR_LOAD_TODAY = "load_consumption_today"
SENSOR_BATTERY_SOC_EOD = "battery_soc_end_of_day"
SENSOR_GRID_IMPORT_TODAY = "grid_import_today"
SENSOR_GRID_EXPORT_TODAY = "grid_export_today"
SENSOR_SELF_SUFFICIENCY = "self_sufficiency_today"
SENSOR_SELF_CONSUMPTION = "self_consumption_today"
SENSOR_SOLAR_TOMORROW_PEAK = "solar_peak_power_tomorrow"
