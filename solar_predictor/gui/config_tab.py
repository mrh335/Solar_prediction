"""
System Configuration tab.

Provides a form-based editor for all system parameters.
Changes are applied in memory and can be saved to YAML.
"""

from __future__ import annotations
import yaml
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton,
    QFileDialog, QScrollArea, QMessageBox, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal


TIMEZONES = [
    "UTC", "Europe/London", "Europe/Berlin", "Europe/Paris",
    "Europe/Madrid", "Europe/Rome", "Europe/Amsterdam",
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Phoenix", "America/Toronto",
    "Australia/Sydney", "Australia/Melbourne", "Asia/Tokyo",
    "Asia/Singapore", "Asia/Dubai",
]


class ConfigTab(QWidget):
    """Tab for viewing and editing the system configuration."""

    config_changed = pyqtSignal(dict)   # emitted when config is applied

    def __init__(self, config: dict, config_path: str, parent=None):
        super().__init__(parent)
        self._config = config
        self._config_path = Path(config_path)
        self._build_ui()
        self._populate(config)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        # ── Location ──────────────────────────────────────────────────────────
        loc_group = QGroupBox("Location")
        loc_form = QFormLayout(loc_group)
        self._lat = self._dbl(-90, 90, 4, "°")
        self._lon = self._dbl(-180, 180, 4, "°")
        self._alt = self._dbl(0, 5000, 0, " m")
        self._tz = QComboBox()
        self._tz.addItems(TIMEZONES)
        self._tz.setEditable(True)
        loc_form.addRow("Latitude:", self._lat)
        loc_form.addRow("Longitude:", self._lon)
        loc_form.addRow("Altitude:", self._alt)
        loc_form.addRow("Timezone:", self._tz)
        layout.addWidget(loc_group)

        # ── Array ─────────────────────────────────────────────────────────────
        arr_group = QGroupBox("Solar Array")
        arr_form = QFormLayout(arr_group)
        self._panel_count = self._int(1, 1000, " panels")
        self._panel_watts = self._dbl(1, 1000, 0, " W STC")
        self._panel_eff = self._dbl(0.01, 0.5, 3, " (fraction)")
        self._temp_coeff = self._dbl(-0.1, 0, 5, " /°C")
        self._noct = self._dbl(20, 70, 0, " °C")
        self._tilt = self._dbl(0, 90, 1, "°")
        self._azimuth = self._dbl(0, 360, 1, "° (180=S)")
        self._losses = self._dbl(0, 0.5, 3, " fraction")
        arr_form.addRow("Panel count:", self._panel_count)
        arr_form.addRow("Rated power (STC):", self._panel_watts)
        arr_form.addRow("Panel efficiency:", self._panel_eff)
        arr_form.addRow("Temp coefficient:", self._temp_coeff)
        arr_form.addRow("NOCT:", self._noct)
        arr_form.addRow("Tilt:", self._tilt)
        arr_form.addRow("Azimuth:", self._azimuth)
        arr_form.addRow("System losses:", self._losses)
        layout.addWidget(arr_group)

        # ── Battery ───────────────────────────────────────────────────────────
        bat_group = QGroupBox("Battery Storage")
        bat_form = QFormLayout(bat_group)
        self._bat_cap = self._dbl(0.1, 500, 1, " kWh")
        self._bat_charge = self._dbl(0.1, 100, 1, " kW")
        self._bat_discharge = self._dbl(0.1, 100, 1, " kW")
        self._bat_charge_eff = self._dbl(0.5, 1.0, 3, "")
        self._bat_discharge_eff = self._dbl(0.5, 1.0, 3, "")
        self._bat_min_soc = self._dbl(0.0, 0.5, 2, "")
        self._bat_max_soc = self._dbl(0.5, 1.0, 2, "")
        self._bat_initial_soc = self._dbl(0.0, 1.0, 2, "")
        bat_form.addRow("Capacity:", self._bat_cap)
        bat_form.addRow("Max charge rate:", self._bat_charge)
        bat_form.addRow("Max discharge rate:", self._bat_discharge)
        bat_form.addRow("Charge efficiency:", self._bat_charge_eff)
        bat_form.addRow("Discharge efficiency:", self._bat_discharge_eff)
        bat_form.addRow("Min SoC:", self._bat_min_soc)
        bat_form.addRow("Max SoC:", self._bat_max_soc)
        bat_form.addRow("Initial SoC (sim):", self._bat_initial_soc)
        layout.addWidget(bat_group)

        # ── Inverter ──────────────────────────────────────────────────────────
        inv_group = QGroupBox("Inverter")
        inv_form = QFormLayout(inv_group)
        self._inv_max = self._dbl(0.1, 100, 1, " kW")
        self._inv_eff = self._dbl(0.5, 1.0, 3, "")
        inv_form.addRow("Max AC power:", self._inv_max)
        inv_form.addRow("Efficiency:", self._inv_eff)
        layout.addWidget(inv_group)

        # ── Load ──────────────────────────────────────────────────────────────
        load_group = QGroupBox("Household Load")
        load_form = QFormLayout(load_group)
        self._annual_kwh = self._dbl(100, 100000, 0, " kWh/year")
        load_form.addRow("Annual consumption:", self._annual_kwh)
        layout.addWidget(load_group)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Buttons
        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("Apply")
        self._save_btn = QPushButton("Save to File")
        self._load_btn = QPushButton("Load from File…")
        for btn in (self._apply_btn, self._save_btn, self._load_btn):
            btn.setFixedHeight(32)
            btn_row.addWidget(btn)
        outer.addLayout(btn_row)

        self._apply_btn.clicked.connect(self._apply)
        self._save_btn.clicked.connect(self._save)
        self._load_btn.clicked.connect(self._load_file)

    # ── Spinbox helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _dbl(lo, hi, decimals, suffix="") -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setSuffix(suffix)
        sb.setFixedHeight(28)
        return sb

    @staticmethod
    def _int(lo, hi, suffix="") -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setSuffix(suffix)
        sb.setFixedHeight(28)
        return sb

    # ── Population ───────────────────────────────────────────────────────────
    def _populate(self, cfg: dict):
        loc = cfg.get("location", {})
        self._lat.setValue(loc.get("latitude", 51.5))
        self._lon.setValue(loc.get("longitude", -0.1))
        self._alt.setValue(loc.get("altitude", 0))
        tz = loc.get("timezone", "UTC")
        idx = self._tz.findText(tz)
        if idx >= 0:
            self._tz.setCurrentIndex(idx)
        else:
            self._tz.setCurrentText(tz)

        arr = cfg.get("array", {})
        pan = arr.get("panels", {})
        self._panel_count.setValue(pan.get("count", 16))
        self._panel_watts.setValue(pan.get("watts_stc", 400))
        self._panel_eff.setValue(pan.get("efficiency", 0.20))
        self._temp_coeff.setValue(pan.get("temp_coefficient", -0.004))
        self._noct.setValue(pan.get("noct", 45))
        self._tilt.setValue(arr.get("tilt", 35))
        self._azimuth.setValue(arr.get("azimuth", 180))
        self._losses.setValue(arr.get("losses", 0.05))

        bat = cfg.get("battery", {})
        self._bat_cap.setValue(bat.get("capacity_kwh", 10))
        self._bat_charge.setValue(bat.get("max_charge_kw", 5))
        self._bat_discharge.setValue(bat.get("max_discharge_kw", 5))
        self._bat_charge_eff.setValue(bat.get("charge_efficiency", 0.96))
        self._bat_discharge_eff.setValue(bat.get("discharge_efficiency", 0.96))
        self._bat_min_soc.setValue(bat.get("min_soc", 0.05))
        self._bat_max_soc.setValue(bat.get("max_soc", 1.0))
        self._bat_initial_soc.setValue(bat.get("initial_soc", 0.5))

        inv = cfg.get("inverter", {})
        self._inv_max.setValue(inv.get("max_power_kw", 6.0))
        self._inv_eff.setValue(inv.get("efficiency", 0.97))

        load = cfg.get("load", {})
        self._annual_kwh.setValue(load.get("annual_kwh", 4500))

    def _collect(self) -> dict:
        return {
            "system": self._config.get("system", {"name": "My Solar System"}),
            "location": {
                "latitude": self._lat.value(),
                "longitude": self._lon.value(),
                "altitude": self._alt.value(),
                "timezone": self._tz.currentText(),
            },
            "array": {
                "panels": {
                    "count": self._panel_count.value(),
                    "watts_stc": self._panel_watts.value(),
                    "efficiency": self._panel_eff.value(),
                    "temp_coefficient": self._temp_coeff.value(),
                    "noct": self._noct.value(),
                },
                "tilt": self._tilt.value(),
                "azimuth": self._azimuth.value(),
                "losses": self._losses.value(),
            },
            "battery": {
                "capacity_kwh": self._bat_cap.value(),
                "max_charge_kw": self._bat_charge.value(),
                "max_discharge_kw": self._bat_discharge.value(),
                "charge_efficiency": self._bat_charge_eff.value(),
                "discharge_efficiency": self._bat_discharge_eff.value(),
                "min_soc": self._bat_min_soc.value(),
                "max_soc": self._bat_max_soc.value(),
                "initial_soc": self._bat_initial_soc.value(),
            },
            "inverter": {
                "max_power_kw": self._inv_max.value(),
                "efficiency": self._inv_eff.value(),
            },
            "load": {
                "annual_kwh": self._annual_kwh.value(),
                "custom_hourly_profile": self._config.get("load", {}).get("custom_hourly_profile"),
            },
            "calibration": self._config.get("calibration", {"production_factor": 1.0, "consumption_factor": 1.0}),
            "weather": self._config.get("weather", {"cache_hours": 1}),
        }

    def _apply(self):
        self._config = self._collect()
        self.config_changed.emit(self._config)

    def _save(self):
        self._apply()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration", str(self._config_path), "YAML files (*.yaml *.yml)"
        )
        if path:
            with open(path, "w") as f:
                yaml.dump(self._config, f, default_flow_style=False)
            QMessageBox.information(self, "Saved", f"Configuration saved to:\n{path}")

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Configuration", str(self._config_path), "YAML files (*.yaml *.yml)"
        )
        if path:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            self._config = cfg
            self._populate(cfg)
            self._apply()
