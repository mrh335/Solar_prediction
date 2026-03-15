"""
Prediction Tab: single-day and multi-day prediction views.

Shows solar production, battery state and grid flows for any chosen date,
pulling weather data from Open-Meteo and running the system simulator.
"""

from __future__ import annotations
import logging
from datetime import date, timedelta

import pandas as pd
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QComboBox, QTabWidget, QProgressBar, QFrame,
    QGridLayout, QSizePolicy,
)

from .chart_widget import ChartWidget, plot_day_overview, plot_day_detail, plot_week_summary

log = logging.getLogger(__name__)


# ── Background worker ─────────────────────────────────────────────────────────

class SimWorker(QObject):
    """Run simulation in a background thread."""
    finished = pyqtSignal(object, object)  # (df, summary) or (df_hourly, df_daily)
    error = pyqtSignal(str)

    def __init__(self, simulator, target_date=None, start=None, end=None):
        super().__init__()
        self._sim = simulator
        self._date = target_date
        self._start = start
        self._end = end

    def run(self):
        try:
            if self._date is not None:
                df, summary = self._sim.simulate_day(self._date)
                self.finished.emit(df, summary)
            else:
                hourly_df, daily_df = self._sim.simulate_range(self._start, self._end)
                self.finished.emit(hourly_df, daily_df)
        except Exception as e:
            log.exception("Simulation failed")
            self.error.emit(str(e))


# ── Summary card widget ───────────────────────────────────────────────────────

class SummaryCard(QFrame):
    """A small card showing a metric value."""
    def __init__(self, label: str, unit: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self._lbl = QLabel(label)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("font-size: 10px; color: #CDD6F4;")
        self._val = QLabel("—")
        self._val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFC107;")
        self._unit = QLabel(unit)
        self._unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unit.setStyleSheet("font-size: 9px; color: #89DCEB;")
        layout.addWidget(self._lbl)
        layout.addWidget(self._val)
        layout.addWidget(self._unit)

    def set_value(self, v: float | str):
        if isinstance(v, float):
            self._val.setText(f"{v:.2f}" if v < 100 else f"{v:.1f}")
        else:
            self._val.setText(str(v))


class PredictionTab(QWidget):
    """Main prediction/visualisation tab."""

    def __init__(self, simulator, parent=None):
        super().__init__(parent)
        self._sim = simulator
        self._current_df: pd.DataFrame | None = None
        self._current_summary: dict | None = None
        self._thread: QThread | None = None
        self._build_ui()

    def update_simulator(self, simulator):
        self._sim = simulator

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Control bar ───────────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("Date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setFixedWidth(120)
        ctrl.addWidget(self._date_edit)

        ctrl.addWidget(QLabel("Range:"))
        self._range_combo = QComboBox()
        self._range_combo.addItems(["Single day", "3 days", "7 days", "14 days", "30 days"])
        self._range_combo.setFixedWidth(110)
        ctrl.addWidget(self._range_combo)

        self._run_btn = QPushButton("⚡  Run Simulation")
        self._run_btn.setFixedHeight(32)
        self._run_btn.setFixedWidth(160)
        self._run_btn.clicked.connect(self._run)
        ctrl.addWidget(self._run_btn)

        self._today_btn = QPushButton("Today")
        self._today_btn.setFixedHeight(32)
        self._today_btn.setFixedWidth(70)
        self._today_btn.clicked.connect(self._goto_today)
        ctrl.addWidget(self._today_btn)

        ctrl.addStretch()

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(120)
        self._progress.setFixedHeight(20)
        self._progress.setVisible(False)
        ctrl.addWidget(self._progress)

        layout.addLayout(ctrl)

        # ── Summary cards ─────────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        self._cards = {
            "solar": SummaryCard("Solar Generated", "kWh"),
            "load": SummaryCard("Load Consumed", "kWh"),
            "self_suff": SummaryCard("Self-Sufficiency", "%"),
            "import": SummaryCard("Grid Import", "kWh"),
            "export": SummaryCard("Grid Export", "kWh"),
            "soc_end": SummaryCard("Battery SoC (end)", "%"),
        }
        for card in self._cards.values():
            cards_row.addWidget(card)
        layout.addLayout(cards_row)

        # ── Chart tabs ────────────────────────────────────────────────────────
        self._chart_tabs = QTabWidget()
        self._chart_tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._overview_chart = ChartWidget(show_toolbar=True)
        self._detail_chart = ChartWidget(show_toolbar=True)
        self._range_chart = ChartWidget(show_toolbar=True)

        self._chart_tabs.addTab(self._overview_chart, "Overview")
        self._chart_tabs.addTab(self._detail_chart, "Weather & Irradiance")
        self._chart_tabs.addTab(self._range_chart, "Multi-Day")
        layout.addWidget(self._chart_tabs)

        # Status bar
        self._status = QLabel("Choose a date and click Run Simulation.")
        self._status.setStyleSheet("color: #89DCEB; font-size: 10px; padding: 2px;")
        layout.addWidget(self._status)

    def _goto_today(self):
        self._date_edit.setDate(QDate.currentDate())

    def _run(self):
        if self._thread and self._thread.isRunning():
            return
        range_map = {"Single day": 1, "3 days": 3, "7 days": 7, "14 days": 14, "30 days": 30}
        days = range_map.get(self._range_combo.currentText(), 1)
        qdate = self._date_edit.date()
        target = date(qdate.year(), qdate.month(), qdate.day())

        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Fetching weather and running simulation…")

        self._thread = QThread()
        if days == 1:
            self._worker = SimWorker(self._sim, target_date=target)
        else:
            end = target + timedelta(days=days - 1)
            self._worker = SimWorker(self._sim, start=target, end=end)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _on_finished(self, first, second):
        if isinstance(second, dict):
            # Single day result
            df, summary = first, second
            self._current_df = df
            self._current_summary = summary
            self._update_cards(summary)
            qdate = self._date_edit.date()
            target = date(qdate.year(), qdate.month(), qdate.day())
            plot_day_overview(self._overview_chart.fig, df, summary, target)
            self._overview_chart.refresh()
            plot_day_detail(self._detail_chart.fig, df, summary)
            self._detail_chart.refresh()
            self._status.setText(
                f"Simulation complete — {target}  |  "
                f"Solar: {summary['solar_kwh']:.2f} kWh  "
                f"Self-sufficiency: {summary['self_sufficiency_pct']:.0f}%"
            )
        else:
            # Multi-day result
            hourly_df, daily_df = first, second
            plot_week_summary(self._range_chart.fig, daily_df)
            self._range_chart.refresh()
            self._chart_tabs.setCurrentWidget(self._range_chart)
            self._status.setText(f"Range simulation complete — {len(daily_df)} days")

    def _on_error(self, msg: str):
        self._status.setText(f"Error: {msg}")

    def _cleanup(self):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)

    def _update_cards(self, summary: dict):
        self._cards["solar"].set_value(summary.get("solar_kwh", 0))
        self._cards["load"].set_value(summary.get("load_kwh", 0))
        self._cards["self_suff"].set_value(summary.get("self_sufficiency_pct", 0))
        self._cards["import"].set_value(summary.get("grid_import_kwh", 0))
        self._cards["export"].set_value(summary.get("grid_export_kwh", 0))
        self._cards["soc_end"].set_value(summary.get("soc_end_pct", 0))
