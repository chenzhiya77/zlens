"""Request-scoped access to singletons assembled by the app factory."""

from fastapi import Request

from zlens.core.config import Settings
from zlens.sources.base import SourceAdapter


def get_source(request: Request) -> SourceAdapter:
    return request.app.state.source


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
