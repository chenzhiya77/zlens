"""Markdown export of the per-model breakdown (T22).

One fixed format, no `format` parameter: this export's destinations are notes,
weekly reports and LLM prompts — md is the right shape, csv would be a second
serializer to maintain for a use case this tool doesn't have. Numbers go out as
raw integers / bare decimals (formatted numbers cannot be recomputed by the
reader), and null cost is written as 未计价, never 0 — exported figures get
pasted into notes and accounts, where a written 0 becomes a "fact".
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response

from zlens.api.deps import get_settings, get_sort, get_source, get_window
from zlens.core.config import Settings
from zlens.core.cost import PriceTable, attach_model_costs
from zlens.sources.models import (
    DateWindow,
    ModelUsageSummary,
    SortColumn,
    SortOrder,
    sort_usage_rows,
)
from zlens.sources.multi import MultiSource

router = APIRouter(prefix="/api", tags=["export"])

_HEADER = """# zlens 按模型明细导出

- 生成时间:{generated_at}
- 口径:输入 / 输出 / 缓存写 / 缓存读 四档互斥、相加等于总计;「输入」只算未命中缓存的部分
  (缓存命中的 token 只按缓存档计价一次);「其中推理」是输出档的组成部分,不额外计费。
- 成本为估算值(人民币,按价格表四档分别乘价);**「未计价」表示价格表中没有该渠道,
  合计里按 0 计入(没填价当免费),实付金额看「买断支出」**。
- 模型别名为浏览器本地状态,不包含在本导出中。
"""


def _money(cost: float | None) -> str:
    if cost is None:
        return "未计价"
    text = f"{cost:.6f}".rstrip("0").rstrip(".")
    return text or "0"


_TABLE_HEADER = (
    "| 来源 | provider_id | 模型 | 请求数 | 输入 | 输出 | 其中推理"
    " | 缓存写 | 缓存读 | 总计 | 成本(估算) |"
    "\n|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"
)


def _render(models: list[ModelUsageSummary], generated_at: str) -> str:
    lines = [
        _HEADER.format(generated_at=generated_at),
        "",
        _TABLE_HEADER,
    ]
    for m in models:
        lines.append(
            f"| {m.source} | {m.provider_id} | {m.model_id} | {m.request_count}"
            f" | {m.input_tokens} | {m.output_tokens} | {m.reasoning_tokens}"
            f" | {m.cache_creation_tokens} | {m.cache_read_tokens} | {m.total_tokens}"
            f" | {_money(m.estimated_cost)} |"
        )
    return "\n".join(lines) + "\n"


@router.get("/export")
def export_models_markdown(
    store: MultiSource = Depends(get_source),
    settings: Settings = Depends(get_settings),
    source: str | None = Query(default=None),
    window: DateWindow | None = Depends(get_window),
    sort: tuple[SortColumn, SortOrder] = Depends(get_sort),
) -> Response:
    table = PriceTable.load(settings.pricing_path)
    models = attach_model_costs(store.select(source).models_ranking(window).models, table)
    rows = sort_usage_rows(models, *sort)
    now = datetime.now().astimezone()
    filename = f"zlens-models-{now.date().isoformat()}.md"
    return Response(
        content=_render(rows, now.isoformat(timespec="seconds")),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
