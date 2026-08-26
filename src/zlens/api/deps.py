"""Request-scoped access to singletons assembled by the app factory."""

from fastapi import Request

from zlens.core.config import Settings
from zlens.sources.multi import MultiSource


def get_source(request: Request) -> MultiSource:
    return request.app.state.source


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
