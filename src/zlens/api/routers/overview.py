from fastapi import APIRouter, Depends

from zlens.api.deps import get_source
from zlens.sources.base import SourceAdapter
from zlens.sources.models import Overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=Overview)
def get_overview(source: SourceAdapter = Depends(get_source)) -> Overview:
    return source.overview()
