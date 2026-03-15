"""
Reusable matplotlib chart widget for embedding in PyQt6.

Provides a clean MatplotlibCanvas that can be dropped into any layout,
plus helper functions for the standard solar/battery charts.
"""

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import QWidget, QVBoxLayout


# ── Colour palette ───────────────────────────────────────────────────────────
COLOUR = {
    "solar": "#FFC107",      # amber
    "load": "#EF5350",       # red
    "battery": "#42A5F5",    # blue
    "grid_import": "#AB47BC",# purple
    "grid_export": "#26A69A",# teal
    "soc": "#66BB6A",        # green
    "sun": "#FFD54F",        # light amber
    "cloud": "#B0BEC5",      # grey-blue
    "temperature": "#FF7043",# deep orange
    "actual": "#4CAF50",     # green (calibration)
    "predicted": "#2196F3",  # blue (calibration)
}

DARK_BG = "#1E1E2E"
PANEL_BG = "#2A2A3E"
TEXT = "#CDD6F4"
GRID = "#45475A"


class MatplotlibCanvas(FigureCanvas):
    """A matplotlib figure embedded in a Qt widget."""

    def __init__(self, parent=None, width=10, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor=DARK_BG)
        super().__init__(self.fig)
        self.setParent(parent)
        self.fig.tight_layout(pad=2.0)

    def clear(self):
        self.fig.clear()
        self.draw()


class ChartWidget(QWidget):
    """
    A widget containing a matplotlib canvas with an optional navigation toolbar.
    """

    def __init__(self, parent=None, show_toolbar=True, width=10, height=6):
        super().__init__(parent)
        self.canvas = MatplotlibCanvas(self, width=width, height=height)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if show_toolbar:
            self.toolbar = NavigationToolbar(self.canvas, self)
            self.toolbar.setStyleSheet(f"background: {PANEL_BG}; color: {TEXT};")
            layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    @property
    def fig(self):
        return self.canvas.fig

    def refresh(self):
        self.canvas.fig.tight_layout(pad=2.0)
        self.canvas.draw()


# ── Chart rendering functions ─────────────────────────────────────────────────

def style_axes(ax, title: str = ""):
    """Apply dark theme styling to an axes object."""
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors=TEXT, labelsize=8)
    ax.title.set_color(TEXT)
    ax.title.set_fontsize(10)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(True, color=GRID, linewidth=0.5, alpha=0.7)
    if title:
        ax.set_title(title)


def plot_day_overview(fig: Figure, df: pd.DataFrame, summary: dict, target_date):
    """
    Main day-view chart: 3 subplots
      1. Solar production vs Load (kW)
      2. Battery SoC (%)
      3. Grid import/export (kW)
    """
    fig.clear()
    fig.patch.set_facecolor(DARK_BG)

    times = df.index.to_pydatetime()
    gs = fig.add_gridspec(3, 1, hspace=0.45, left=0.08, right=0.97, top=0.93, bottom=0.08)

    # ── Subplot 1: Production & Load ──────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])
    ax1.fill_between(times, df["solar_kw"], alpha=0.6, color=COLOUR["solar"], label="Solar")
    ax1.fill_between(times, df["load_kw"], alpha=0.4, color=COLOUR["load"], label="Load")
    ax1.plot(times, df["solar_kw"], color=COLOUR["solar"], linewidth=1.5)
    ax1.plot(times, df["load_kw"], color=COLOUR["load"], linewidth=1.5)
    ax1.set_ylabel("Power (kW)", color=TEXT, fontsize=8)
    style_axes(ax1, f"Solar & Load  |  {target_date}")
    ax1.legend(loc="upper left", fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT,
               edgecolor=GRID, ncol=2)
    _format_time_axis(ax1)

    # ── Subplot 2: Battery SoC ─────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    ax2.fill_between(times, df["soc_pct"], alpha=0.5, color=COLOUR["soc"])
    ax2.plot(times, df["soc_pct"], color=COLOUR["soc"], linewidth=2)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Battery SoC (%)", color=TEXT, fontsize=8)
    style_axes(ax2, "Battery State of Charge")
    _format_time_axis(ax2)
    # Mark start/end SoC
    ax2.annotate(
        f"Start: {summary['soc_start_pct']:.0f}%",
        xy=(times[0], df['soc_pct'].iloc[0]),
        xytext=(6, 6), textcoords='offset points',
        fontsize=7, color=TEXT,
    )

    # ── Subplot 3: Grid import/export ─────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2])
    grid = df["grid_kw"]
    import_ = grid.clip(lower=0)
    export_ = (-grid).clip(lower=0)
    ax3.fill_between(times, import_, alpha=0.6, color=COLOUR["grid_import"], label="Import")
    ax3.fill_between(times, -export_, alpha=0.6, color=COLOUR["grid_export"], label="Export")
    ax3.axhline(0, color=GRID, linewidth=0.8)
    ax3.set_ylabel("Power (kW)", color=TEXT, fontsize=8)
    style_axes(ax3, "Grid  (Import = +, Export = -)")
    ax3.legend(loc="upper left", fontsize=7, facecolor=PANEL_BG, labelcolor=TEXT,
               edgecolor=GRID, ncol=2)
    _format_time_axis(ax3)


def plot_day_detail(fig: Figure, df: pd.DataFrame, summary: dict):
    """
    Detailed view with sun elevation, cloud cover, and temperature overlaid.
    """
    fig.clear()
    fig.patch.set_facecolor(DARK_BG)

    times = df.index.to_pydatetime()
    gs = fig.add_gridspec(2, 2, hspace=0.45, wspace=0.35,
                          left=0.08, right=0.97, top=0.93, bottom=0.08)

    # Sun elevation
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.fill_between(times, df["sun_elevation_deg"].clip(lower=0),
                     alpha=0.6, color=COLOUR["sun"])
    ax1.set_ylabel("Elevation (°)", color=TEXT, fontsize=8)
    style_axes(ax1, "Sun Elevation")
    _format_time_axis(ax1)

    # Cloud cover
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.fill_between(times, df["cloud_cover_pct"], alpha=0.7, color=COLOUR["cloud"])
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("Cloud Cover (%)", color=TEXT, fontsize=8)
    style_axes(ax2, "Cloud Cover")
    _format_time_axis(ax2)

    # Temperature
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(times, df["temp_c"], color=COLOUR["temperature"], linewidth=2)
    ax3.fill_between(times, df["temp_c"], alpha=0.3, color=COLOUR["temperature"])
    ax3.set_ylabel("Temperature (°C)", color=TEXT, fontsize=8)
    style_axes(ax3, "Ambient Temperature")
    _format_time_axis(ax3)

    # Irradiance (GHI/DNI/DHI)
    ax4 = fig.add_subplot(gs[1, 1])
    if "ghi" in df.columns:
        ax4.plot(times, df["ghi"], label="GHI", color="#FFD54F", linewidth=1.5)
        ax4.plot(times, df["dhi"], label="DHI", color="#FF8A65", linewidth=1.2)
        ax4.plot(times, df["dni"], label="DNI", color="#FFF176", linewidth=1.0, linestyle="--")
        ax4.legend(loc="upper left", fontsize=7, facecolor=PANEL_BG,
                   labelcolor=TEXT, edgecolor=GRID)
    ax4.set_ylabel("Irradiance (W/m²)", color=TEXT, fontsize=8)
    style_axes(ax4, "Solar Irradiance Components")
    _format_time_axis(ax4)


def plot_week_summary(fig: Figure, daily_df: pd.DataFrame):
    """Bar chart of daily energy totals over a week or month."""
    fig.clear()
    fig.patch.set_facecolor(DARK_BG)

    ax = fig.add_subplot(111)
    dates = list(daily_df.index)
    x = np.arange(len(dates))
    w = 0.22

    ax.bar(x - w, daily_df.get("solar_kwh", 0), width=w, label="Solar", color=COLOUR["solar"], alpha=0.85)
    ax.bar(x,     daily_df.get("load_kwh", 0),  width=w, label="Load",  color=COLOUR["load"],  alpha=0.85)
    ax.bar(x + w, daily_df.get("grid_import_kwh", 0), width=w, label="Grid Import",
           color=COLOUR["grid_import"], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([str(d) for d in dates], rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Energy (kWh)", color=TEXT, fontsize=9)
    style_axes(ax, "Daily Energy Summary")
    ax.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT, edgecolor=GRID)

    fig.tight_layout(pad=2.0)


def plot_calibration_comparison(fig: Figure, comparison_df: pd.DataFrame, title: str = ""):
    """Scatter + time-series view for calibration: real vs predicted."""
    fig.clear()
    fig.patch.set_facecolor(DARK_BG)
    has_production = "real_production_kw" in comparison_df.columns
    has_consumption = "real_consumption_kw" in comparison_df.columns
    n_plots = has_production + has_consumption
    if n_plots == 0:
        return

    axes = fig.subplots(n_plots, 1, squeeze=False)
    fig.subplots_adjust(hspace=0.4, left=0.1, right=0.97, top=0.92, bottom=0.1)
    times = comparison_df.index.to_pydatetime()
    plot_idx = 0

    if has_production:
        ax = axes[plot_idx][0]
        ax.plot(times, comparison_df["predicted_production_kw"],
                color=COLOUR["predicted"], linewidth=1.5, label="Predicted")
        ax.plot(times, comparison_df["real_production_kw"],
                color=COLOUR["actual"], linewidth=1.5, label="Actual", linestyle="--")
        ax.set_ylabel("Production (kW)", color=TEXT, fontsize=8)
        style_axes(ax, "Production: Actual vs Predicted")
        ax.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT, edgecolor=GRID)
        _format_time_axis(ax)
        plot_idx += 1

    if has_consumption:
        ax = axes[plot_idx][0]
        ax.plot(times, comparison_df["predicted_load_kw"],
                color=COLOUR["predicted"], linewidth=1.5, label="Predicted")
        ax.plot(times, comparison_df["real_consumption_kw"],
                color=COLOUR["actual"], linewidth=1.5, label="Actual", linestyle="--")
        ax.set_ylabel("Consumption (kW)", color=TEXT, fontsize=8)
        style_axes(ax, "Consumption: Actual vs Predicted")
        ax.legend(fontsize=8, facecolor=PANEL_BG, labelcolor=TEXT, edgecolor=GRID)
        _format_time_axis(ax)


def _format_time_axis(ax):
    """Format x-axis with hour labels."""
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    for label in ax.xaxis.get_ticklabels():
        label.set_color(TEXT)
        label.set_fontsize(7)
