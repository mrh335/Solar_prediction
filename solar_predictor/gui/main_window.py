"""
Main application window for the Solar Predictor GUI.

Layout:
  - Toolbar with quick actions
  - Tab widget: Prediction | Weather Details | Multi-Day | Configuration | Calibration
  - Status bar with system info and clock
"""

from __future__ import annotations
import logging
from pathlib import Path

import yaml
from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel,
    QToolBar, QMessageBox, QFileDialog,
)

from .prediction_tab import PredictionTab
from .config_tab import ConfigTab
from .calibration_tab import CalibrationTab
from ..core.system_sim import SystemSimulator

log = logging.getLogger(__name__)

APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1E1E2E;
    color: #CDD6F4;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 11px;
}
QTabWidget::pane {
    border: 1px solid #45475A;
    background: #1E1E2E;
}
QTabBar::tab {
    background: #2A2A3E;
    color: #CDD6F4;
    padding: 6px 16px;
    border: 1px solid #45475A;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #313244;
    color: #CBA6F7;
    border-top: 2px solid #CBA6F7;
}
QPushButton {
    background: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 4px 10px;
}
QPushButton:hover { background: #45475A; }
QPushButton:pressed { background: #585B70; }
QPushButton:disabled { color: #6C7086; }
QGroupBox {
    border: 1px solid #45475A;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
    color: #89B4FA;
}
QGroupBox::title { subcontrol-origin: margin; padding: 0 4px; left: 8px; }
QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QDateEdit {
    background: #313244;
    border: 1px solid #45475A;
    border-radius: 3px;
    padding: 2px 4px;
    color: #CDD6F4;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus,
QComboBox:focus, QDateEdit:focus { border-color: #89B4FA; }
QScrollBar:vertical {
    background: #1E1E2E; width: 10px; border: none;
}
QScrollBar::handle:vertical { background: #45475A; border-radius: 5px; }
QStatusBar { background: #181825; color: #CDD6F4; }
QToolBar { background: #181825; border-bottom: 1px solid #45475A; spacing: 4px; }
QTextEdit { background: #313244; border: 1px solid #45475A; border-radius: 3px; }
QProgressBar {
    background: #313244; border: 1px solid #45475A;
    border-radius: 3px; text-align: center;
}
QProgressBar::chunk { background: #89B4FA; border-radius: 3px; }
QSplitter::handle { background: #45475A; }
QFrame[frameShape="5"] { color: #45475A; }
"""


class MainWindow(QMainWindow):
    """The main application window."""

    def __init__(self, config: dict, config_path: str):
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._simulator = SystemSimulator(config)

        self.setWindowTitle("Solar Predictor")
        self.setMinimumSize(1100, 750)
        self.resize(1280, 820)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_menu()
        self._build_toolbar()
        self._build_tabs()
        self._build_statusbar()
        self._start_clock()

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("background: #181825; color: #CDD6F4; border-bottom: 1px solid #45475A;")

        file_menu = menubar.addMenu("&File")
        open_cfg = QAction("Open Configuration…", self)
        open_cfg.triggered.connect(self._open_config)
        file_menu.addAction(open_cfg)
        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = menubar.addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._about)
        help_menu.addAction(about_act)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._sys_label = QLabel("  System: loading…  ")
        self._sys_label.setStyleSheet("color: #CBA6F7; font-size: 11px; padding: 2px 8px;")
        tb.addWidget(self._sys_label)
        self._update_system_label()

    def _update_system_label(self):
        arr = self._config.get("array", {})
        pan = arr.get("panels", {})
        kwp = pan.get("count", 0) * pan.get("watts_stc", 0) / 1000
        cap = self._config.get("battery", {}).get("capacity_kwh", 0)
        loc = self._config.get("location", {})
        name = self._config.get("system", {}).get("name", "Solar System")
        self._sys_label.setText(
            f"  {name}  |  {kwp:.2f} kWp  |  {cap} kWh battery  |  "
            f"Lat {loc.get('latitude', '?')} Lon {loc.get('longitude', '?')}  "
        )

    def _build_tabs(self):
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._pred_tab = PredictionTab(self._simulator)
        self._cfg_tab = ConfigTab(self._config, self._config_path)
        self._cal_tab = CalibrationTab(self._simulator)

        tabs.addTab(self._pred_tab, "Prediction & Charts")
        tabs.addTab(self._cal_tab, "Calibration")
        tabs.addTab(self._cfg_tab, "Configuration")

        # Wire signals
        self._cfg_tab.config_changed.connect(self._on_config_changed)
        self._cal_tab.factors_updated.connect(self._on_factors_updated)

        self.setCentralWidget(tabs)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._clock_label = QLabel()
        self._clock_label.setStyleSheet("color: #89DCEB; padding-right: 8px;")
        sb.addPermanentWidget(self._clock_label)

    def _start_clock(self):
        timer = QTimer(self)
        timer.timeout.connect(self._update_clock)
        timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        self._clock_label.setText(
            QDateTime.currentDateTime().toString("yyyy-MM-dd  HH:mm:ss")
        )

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_config_changed(self, config: dict):
        self._config = config
        self._simulator = SystemSimulator(config)
        self._pred_tab.update_simulator(self._simulator)
        self._cal_tab.update_simulator(self._simulator)
        self._update_system_label()

    def _on_factors_updated(self, prod_factor: float, cons_factor: float):
        cal = self._config.setdefault("calibration", {})
        cal["production_factor"] = prod_factor
        cal["consumption_factor"] = cons_factor
        # Rebuild simulator with updated calibration
        self._on_config_changed(self._config)

    def _open_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Configuration", self._config_path, "YAML files (*.yaml *.yml)"
        )
        if path:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            self._on_config_changed(cfg)

    def _about(self):
        QMessageBox.about(
            self,
            "About Solar Predictor",
            "<h3>Solar Predictor v1.0</h3>"
            "<p>A professional solar production, consumption and battery storage "
            "prediction tool.</p>"
            "<p>Uses <b>pvlib</b> for solar physics, <b>Open-Meteo</b> for weather data, "
            "and real system parameters for accurate predictions.</p>"
            "<p>Supports Home Assistant integration as a custom component.</p>",
        )
