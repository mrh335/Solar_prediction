#!/usr/bin/env python3
"""
Solar Predictor - Entry point.

Launches the PyQt6 GUI application.

Usage:
    python main.py [--config path/to/config.yaml]

Options:
    --config    Path to a YAML configuration file (default: config/default_config.yaml)
    --help      Show this message
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quieten noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pvlib").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def load_config(path: str) -> dict:
    """Load YAML config, merging with defaults where keys are missing."""
    default_path = Path(__file__).parent / "config" / "default_config.yaml"
    with open(default_path) as f:
        config = yaml.safe_load(f)

    if Path(path).exists() and path != str(default_path):
        with open(path) as f:
            user_config = yaml.safe_load(f)
        # Deep merge user config over defaults
        _deep_merge(config, user_config)
    return config


def _deep_merge(base: dict, override: dict):
    """Recursively merge override into base (in-place)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def main():
    setup_logging()
    log = logging.getLogger("solar_predictor")

    parser = argparse.ArgumentParser(description="Solar Predictor")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent / "config" / "default_config.yaml"),
        help="Path to YAML configuration file",
    )
    args = parser.parse_args()

    log.info("Loading configuration from: %s", args.config)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        log.error("Configuration file not found: %s", args.config)
        sys.exit(1)
    except yaml.YAMLError as e:
        log.error("Invalid YAML in config file: %s", e)
        sys.exit(1)

    # Import Qt here (after logging is set up) so any Qt import errors are caught
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
    except ImportError:
        log.error(
            "PyQt6 is not installed. Install it with: pip install PyQt6"
        )
        sys.exit(1)

    from solar_predictor.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Solar Predictor")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")  # Cross-platform consistent look

    window = MainWindow(config, args.config)
    window.show()

    log.info("Solar Predictor started.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
