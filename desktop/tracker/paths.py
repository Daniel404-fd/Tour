"""Пути к ресурсам — и при запуске из исходников, и из собранного .exe."""
import sys
from pathlib import Path

APP_VERSION = "2.8.1"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "tracker" / "resources" / name
