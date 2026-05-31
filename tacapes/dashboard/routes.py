"""Route handlers, split out so each phase can append cleanly."""
from __future__ import annotations

from fastapi import FastAPI


def register(app: FastAPI) -> None:
    """Hooked from create_app(). Each task appends its routes here."""
    pass
