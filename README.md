# Solar Predictor

A professional Python tool for predicting solar PV production, household consumption,
and battery storage state for any date — with a full GUI and Home Assistant integration.

---

## Features

- **Physics-based solar model** using [pvlib](https://pvlib-python.readthedocs.io/):
  - Accurate sun position (ephemeris/SPA) for any location and date
  - Clear-sky irradiance (Ineichen model)
  - Plane-of-array irradiance for any tilt and azimuth (Hay-Davies transposition)
  - Cell temperature correction (Faiman model)
  - Inverter DC→AC conversion with clipping

- **Real weather data** from [Open-Meteo](https://open-meteo.com/) (free, no API key):
  - GHI, DNI, DHI irradiance
  - Cloud cover, temperature, wind speed
  - 16-day hourly forecast + historical archive

- **Battery storage simulation**:
  - Solar-first self-consumption strategy
  - Configurable capacity, charge/discharge rates, efficiency
  - Grid import/export tracking

- **Calibration** from your real measured data:
  - Import CSV from inverter or Home Assistant history
  - Auto-detects column formats
  - Derives production and consumption correction factors

- **PyQt6 GUI** with dark theme:
  - Single-day prediction with power flow charts
  - Weather & irradiance detail charts
  - Multi-day (week/month) bar chart summary
  - Configuration editor
  - Calibration tool

- **Home Assistant custom integration**:
  - 10 sensors (production today/tomorrow, battery SoC, self-sufficiency, grid flows, …)
  - Hourly updates via coordinator
  - Config flow UI

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your system

Edit `config/default_config.yaml` (or copy it and use `--config`):

```yaml
location:
  latitude: 51.5074       # Your latitude
  longitude: -0.1278      # Your longitude
  altitude: 50            # Metres above sea level
  timezone: "Europe/London"

array:
  panels:
    count: 16             # Number of panels
    watts_stc: 405        # Rated power per panel (W)
    temp_coefficient: -0.0035
    noct: 45
  tilt: 35                # Degrees from horizontal
  azimuth: 180            # 180 = south-facing

battery:
  capacity_kwh: 10.0
  max_charge_kw: 5.0
  max_discharge_kw: 5.0

load:
  annual_kwh: 4500        # Annual household consumption
```

### 3. Launch the GUI

```bash
python main.py
# or with a custom config:
python main.py --config /path/to/my_system.yaml
```

---

## Calibrating with Real Data

1. Export data from your inverter/monitoring system as CSV
2. The CSV should contain a timestamp column and a power/energy column
3. Go to the **Calibration** tab in the GUI
4. Click **Browse CSV…** and select your file
5. Click **Calibrate** — the tool will compare real vs predicted data
6. Click **Apply Factors** to use the derived correction factors

**Supported column names** (auto-detected):
- Timestamps: `time`, `timestamp`, `datetime`, `date`, `local_time`, …
- Production: `solar`, `pv`, `production`, `generated`, `solar_kw`, `p_ac`, …
- Consumption: `load`, `consumption`, `demand`, `usage`, `home_consumption`, …

---

## Home Assistant Integration

### Installation

1. Copy the integration to your HA config directory:
   ```bash
   cp -r solar_predictor/ha_integration \
         /path/to/homeassistant/config/custom_components/solar_predictor
   ```

2. Copy your `config.yaml` to a location accessible by HA:
   ```bash
   cp config/default_config.yaml \
      /path/to/homeassistant/config/solar_predictor_config.yaml
   ```
   Edit it to match your system.

3. In Home Assistant: **Settings → Devices & Services → Add Integration** → search for "Solar Predictor"

4. Enter the full path to your config YAML file (e.g. `/config/solar_predictor_config.yaml`)

### Exposed Sensors

| Sensor | Unit | Description |
|--------|------|-------------|
| `solar_predictor_production_today` | kWh | Predicted solar production for today |
| `solar_predictor_production_tomorrow` | kWh | Predicted solar production for tomorrow |
| `solar_predictor_current_hour_power` | kW | Predicted power this hour |
| `solar_predictor_tomorrow_peak_power` | kW | Expected peak power tomorrow |
| `solar_predictor_load_today` | kWh | Predicted household consumption |
| `solar_predictor_battery_soc_end_of_day` | % | Predicted battery SoC at end of day |
| `solar_predictor_grid_import_today` | kWh | Predicted grid import |
| `solar_predictor_grid_export_today` | kWh | Predicted grid export |
| `solar_predictor_self_sufficiency_today` | % | Self-sufficiency percentage |
| `solar_predictor_self_consumption_today` | % | Self-consumption percentage |

---

## Project Structure

```
Solar_prediction/
├── main.py                          # GUI entry point
├── requirements.txt
├── setup.py
├── config/
│   └── default_config.yaml          # System configuration template
├── data/                            # Local data (calibration CSVs, etc.)
└── solar_predictor/
    ├── core/
    │   ├── solar_model.py           # pvlib solar physics
    │   ├── weather_api.py           # Open-Meteo API client
    │   ├── battery_model.py         # Battery storage simulation
    │   ├── system_sim.py            # Full system orchestrator
    │   └── calibration.py           # Real data import & calibration
    ├── gui/
    │   ├── main_window.py           # PyQt6 main window
    │   ├── prediction_tab.py        # Day/range prediction view
    │   ├── config_tab.py            # Configuration editor
    │   ├── calibration_tab.py       # Calibration UI
    │   └── chart_widget.py          # Matplotlib chart components
    └── ha_integration/              # Home Assistant custom component
        ├── __init__.py
        ├── manifest.json
        ├── const.py
        ├── config_flow.py
        ├── sensor.py
        └── strings.json
```

---

## Physics Notes

**Irradiance chain:**
```
Clear-sky GHI/DNI/DHI (Ineichen)
  → Weather-adjusted by Open-Meteo measured irradiance
  → Transposed to POA on tilted surface (Hay-Davies)
  → Cell temperature (Faiman model)
  → DC power: P = (G/1000) × kWp × (1 + γ(T_cell − 25)) × (1 − losses)
  → AC power: P_AC = P_DC × η_inverter  [clamped to inverter max]
```

**Battery strategy:** Solar-first self-consumption
1. Solar satisfies load directly
2. Surplus charges battery (rate-limited, SoC-limited)
3. Remaining surplus exported to grid
4. Deficit draws from battery first, then grid
