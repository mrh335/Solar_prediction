from setuptools import setup, find_packages

setup(
    name="solar-predictor",
    version="1.0.0",
    description="Solar production, consumption and battery storage predictor with GUI and Home Assistant integration",
    author="mrh335",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "pvlib>=0.10.0",
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "matplotlib>=3.7.0",
        "PyQt6>=6.4.0",
        "requests>=2.28.0",
        "pyyaml>=6.0",
        "scipy>=1.10.0",
        "pytz>=2023.3",
        "requests-cache>=1.1.0",
    ],
    entry_points={
        "console_scripts": [
            "solar-predictor=main:main",
        ],
    },
    python_requires=">=3.10",
)
