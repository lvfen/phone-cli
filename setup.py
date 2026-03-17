#!/usr/bin/env python3
"""Setup script for phone-cli."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="phone-cli",
    version="0.1.0",
    description="CLI tool for AI-powered phone automation via ADB, HDC, and iOS",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "Pillow>=12.0.0",
        "click>=8.0.0",
    ],
    extras_require={
        "ios": [
            "tidevice>=0.12.0",
            "facebook-wda>=1.4.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "phone-cli=phone_cli.cli.main:cli",
        ],
    },
)
