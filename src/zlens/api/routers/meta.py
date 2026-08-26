from fastapi import APIRouter, Depends

from zlens.api.deps import get_source
from zlens.sources.base import SourceAdapter
from zlens.sources.models import MetaInfo

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta", response_model=MetaInfo)
def get_meta(source: SourceAdapter = Depends(get_source)) -> MetaInfo:
    return source.meta()
