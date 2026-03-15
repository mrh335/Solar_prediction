"""
Calibration Tab: import real measured data, compare against predictions,
and derive / apply correction factors.
"""

from __future__ import annotations
import logging
from datetime import date

import pandas as pd
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QFileDialog, QGroupBox, QFormLayout, QDoubleSpinBox,
    QTextEdit, QSplitter, QSizePolicy, QMessageBox, QProgressBar,
)

from .chart_widget import ChartWidget, plot_calibration_comparison
from ..core.calibration import load_csv, Calibrator

log = logging.getLogger(__name__)


class CalibrationWorker(QObject):
    finished = pyqtSignal(object, object)  # (factors_dict, comparison_df or None)
    error = pyqtSignal(str)

    def __init__(self, calibrator, real_df, compare_date=None):
        super().__init__()
        self._cal = calibrator
        self._real_df = real_df
        self._compare_date = compare_date

    def run(self):
        try:
            factors = self._cal.compute_factors(self._real_df)
            comp = None
            if self._compare_date:
                try:
                    comp = self._cal.compare_day(self._compare_date, self._real_df)
                except Exception as e:
                    log.warning("Could not generate comparison: %s", e)
            self.finished.emit(factors, comp)
        except Exception as e:
            log.exception("Calibration failed")
            self.error.emit(str(e))


class CalibrationTab(QWidget):
    """Tab for importing real data and calibrating the model."""

    factors_updated = pyqtSignal(float, float)   # (prod_factor, cons_factor)

    def __init__(self, simulator, parent=None):
        super().__init__(parent)
        self._sim = simulator
        self._real_df: pd.DataFrame | None = None
        self._thread: QThread | None = None
        self._build_ui()

    def update_simulator(self, simulator):
        self._sim = simulator

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Top panel: controls ───────────────────────────────────────────────
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setSpacing(6)

        # File import
        import_group = QGroupBox("1. Import Measured Data")
        import_layout = QHBoxLayout(import_group)
        self._file_label = QLabel("No file loaded")
        self._file_label.setStyleSheet("color: #89DCEB;")
        import_layout.addWidget(self._file_label)
        browse_btn = QPushButton("Browse CSV…")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        import_layout.addWidget(browse_btn)
        top_layout.addWidget(import_group)

        # Data info
        self._info_box = QTextEdit()
        self._info_box.setFixedHeight(70)
        self._info_box.setReadOnly(True)
        self._info_box.setStyleSheet("font-family: monospace; font-size: 10px;")
        self._info_box.setPlaceholderText("Loaded data summary will appear here…")
        top_layout.addWidget(self._info_box)

        # Calibration settings + run
        cal_group = QGroupBox("2. Run Calibration")
        cal_layout = QFormLayout(cal_group)
        self._compare_date = QDateEdit()
        self._compare_date.setDisplayFormat("yyyy-MM-dd")
        self._compare_date.setCalendarPopup(True)
        self._compare_date.setDate(QDate.currentDate().addDays(-1))
        cal_layout.addRow("Compare date:", self._compare_date)
        run_row = QHBoxLayout()
        self._run_btn = QPushButton("Calibrate")
        self._run_btn.setFixedHeight(30)
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_calibration)
        run_row.addWidget(self._run_btn)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(100)
        self._progress.setVisible(False)
        run_row.addWidget(self._progress)
        run_row.addStretch()
        cal_layout.addRow("", run_row)
        top_layout.addWidget(cal_group)

        # Results + manual override
        results_group = QGroupBox("3. Calibration Results & Override")
        results_layout = QFormLayout(results_group)
        self._prod_factor = QDoubleSpinBox()
        self._prod_factor.setRange(0.1, 5.0)
        self._prod_factor.setDecimals(4)
        self._prod_factor.setValue(1.0)
        self._cons_factor = QDoubleSpinBox()
        self._cons_factor.setRange(0.1, 5.0)
        self._cons_factor.setDecimals(4)
        self._cons_factor.setValue(1.0)
        results_layout.addRow("Production factor:", self._prod_factor)
        results_layout.addRow("Consumption factor:", self._cons_factor)
        apply_btn = QPushButton("Apply Factors")
        apply_btn.setFixedHeight(28)
        apply_btn.clicked.connect(self._apply_factors)
        results_layout.addRow("", apply_btn)
        self._result_label = QLabel("")
        self._result_label.setStyleSheet("color: #A6E3A1; font-size: 10px;")
        results_layout.addRow("", self._result_label)
        top_layout.addWidget(results_group)

        splitter.addWidget(top)

        # ── Bottom panel: comparison chart ────────────────────────────────────
        chart_container = QWidget()
        chart_vbox = QVBoxLayout(chart_container)
        chart_vbox.setContentsMargins(0, 0, 0, 0)
        chart_vbox.addWidget(QLabel("Actual vs Predicted Comparison:"))
        self._chart = ChartWidget(show_toolbar=True, height=5)
        chart_vbox.addWidget(self._chart)
        splitter.addWidget(chart_container)
        splitter.setSizes([380, 320])

        layout.addWidget(splitter)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Data CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            self._real_df = load_csv(path)
            self._file_label.setText(path.split("/")[-1])
            dates = self._real_df.index.date
            cols = list(self._real_df.columns)
            self._info_box.setPlainText(
                f"Rows: {len(self._real_df):,}  |  "
                f"Columns: {', '.join(cols)}\n"
                f"Date range: {dates.min()} → {dates.max()}\n"
                f"Detected: {', '.join(cols)}"
            )
            self._run_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "Load Failed", str(e))

    def _run_calibration(self):
        if self._real_df is None or (self._thread and self._thread.isRunning()):
            return
        qdate = self._compare_date.date()
        compare_date = date(qdate.year(), qdate.month(), qdate.day())

        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._result_label.setText("Running…")

        calibrator = Calibrator(self._sim)
        self._thread = QThread()
        self._worker = CalibrationWorker(calibrator, self._real_df, compare_date)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()

    def _on_done(self, factors: dict, comparison):
        self._prod_factor.setValue(factors.get("production_factor", 1.0))
        self._cons_factor.setValue(factors.get("consumption_factor", 1.0))
        n_prod = factors.get("production_factor_n", 0)
        n_cons = factors.get("consumption_factor_n", 0)
        self._result_label.setText(
            f"Production factor: {factors['production_factor']:.4f} (from {n_prod} days)   "
            f"Consumption factor: {factors['consumption_factor']:.4f} (from {n_cons} days)"
        )
        if comparison is not None and not comparison.empty:
            plot_calibration_comparison(self._chart.fig, comparison)
            self._chart.refresh()

    def _on_error(self, msg: str):
        self._result_label.setText(f"Error: {msg}")
        QMessageBox.warning(self, "Calibration Error", msg)

    def _cleanup(self):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)

    def _apply_factors(self):
        pf = self._prod_factor.value()
        cf = self._cons_factor.value()
        self.factors_updated.emit(pf, cf)
        self._result_label.setText(
            f"Applied: production_factor={pf:.4f}, consumption_factor={cf:.4f}"
        )
