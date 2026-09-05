"""Data contracts produced by source adapters and served by the API.

Row-level models carry `source` so multi-source merges stay attributable
(see docs/specs/v2-multi-source-spec.md).

Token buckets are mutually exclusive by contract: `input_tokens` counts only the
prompt tokens that were *not* served from cache, `output_tokens` counts everything
billed at the output price (reasoning included, hence `reasoning_tokens` is a
breakdown of it, never an extra bucket), and `cache_creation_tokens` /
`cache_read_tokens` are their own priced tiers. The four sum to `total_tokens`.
Costing multiplies each bucket by its own unit price, so a source that reports the
cached prefix *inside* its input must subtract it in its adapter — leaving it
nested charges those tokens twice, at the full input price.

Credits are the third ledger (v3): `credits`/`original_credits` carry
upstream-reported credit amounts (Qoder CN CLI, WorkBuddy) and are priced via
`credit_prices` (`source|basis` keys), never folded into `estimated_cost`.
`tokens_reported=False` marks sources whose token buckets are structurally
absent (upstream never sends tokens): the zeros are placeholders, must not be
priced, and the source must surface in "未计入 token 口径" hints. `None` means
"not reported" — strictly distinct from 0.
"""

from dataclasses import dataclass
from datetime import date, datetime
from operator import attrgetter
from typing import Literal

from pydantic import BaseModel


def model_key(source: str, provider_id: str, model_id: str) -> str:
    """Canonical channel identity: 'source|provider_id|model_id'.

    The price table and display aliases both address a channel by this key, so
    the same model id served through two channels never shares one price.
    """
    return f"{source}|{provider_id}|{model_id}"


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Closed local-day window [start, end]; a None bound is unbounded.

    The API accepts only absolute ISO dates — a relative expression like "近 7 天"
    is the frontend's to translate, because its anchor (today vs the last request)
    is a product decision, not an API guess. Default (no window) means the full
    history, so "全部" needs no special branch anywhere downstream.
    """

    start: date | None = None
    end: date | None = None

    def contains_day(self, day: str) -> bool:
        """Membership for a 'YYYY-MM-DD' local-day string as produced by the
        adapters' day cut (SQL date(...) or ms_to_local_day)."""
        return (self.start is None or day >= self.start.isoformat()) and (
            self.end is None or day <= self.end.isoformat()
        )


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """Half-open instant window [since, until) for the runtime-quality endpoints
    (T27); a None bound is unbounded.

    Unlike DateWindow this is hour-level and closed-open on purpose: a date-level
    custom range maps to [day 00:00, day+1 00:00) without fabricating a
    23:59:59.999 bound. Naive datetimes are local time — the app's only clock.
    The API accepts only absolute instants; a relative "近 1 小时" is the
    frontend's to translate (same split as DateWindow), and it re-translates on
    every fetch so a monitoring preset slides with now instead of pinning to the
    moment it was picked.
    """

    since: datetime | None = None
    until: datetime | None = None

    def since_ms(self) -> int | None:
        """Inclusive lower bound as UTC epoch ms (None = unbounded)."""
        return int(self.since.timestamp() * 1000) if self.since is not None else None

    def until_ms(self) -> int | None:
        """Exclusive upper bound as UTC epoch ms (None = unbounded)."""
        return int(self.until.timestamp() * 1000) if self.until is not None else None

    def contains_ms(self, ms: int) -> bool:
        """Membership for a UTC epoch-ms request timestamp."""
        return not (
            (self.since is not None and ms < self.since_ms())
            or (self.until is not None and ms >= self.until_ms())
        )


class ModelUsageSummary(BaseModel):
    source: str = "zcode"
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    # Third ledger (v3): upstream-reported credits, priced via `credit_prices`
    # (source|basis), never folded into estimated_cost. None = the source does
    # not report credits — strictly distinct from 0.0 (a real zero, e.g. a free
    # in-house model row).
    credits: float | None = None
    # List-price credits before the per-row discount (Qoder CN reports both).
    original_credits: float | None = None
    # False = the token buckets above are structurally absent (upstream never
    # sends tokens): the zeros are placeholders, must not be priced, and the
    # source belongs in "未计入 token 口径" hints.
    tokens_reported: bool = True
    # Adapter declaration: this source reports credits at all.
    credits_reported: bool = False
    # cache_read / (input + cache_read + cache_creation): share of the prompt
    # tokens served from cache. Denominator 0 -> None (not 0%, not 100%).
    cache_hit_rate: float | None = None


SortColumn = Literal[
    "request_count",
    "input_tokens",
    "output_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "total_tokens",
    "estimated_cost",
]
SortOrder = Literal["desc", "asc"]

# Only estimated_cost carries the unpriced-last rule; every other sortable field
# is an upstream-reported fact with no unknown values to sink.
_TOKEN_FIELDS = frozenset(
    {"input_tokens", "output_tokens", "cache_creation_tokens", "cache_read_tokens", "total_tokens"}
)


def sort_usage_rows(
    rows: list["ModelUsageSummary"], sort: SortColumn, order: SortOrder
) -> list["ModelUsageSummary"]:
    """Backend-side table sort (T19): the unpriced-last rule lives here, server
    side, so no client re-sort can ever mix "unknown cost" into the middle of a
    cost ranking where it would read as "cheap" instead of "unpriced".
    """
    reverse = order == "desc"
    if sort == "estimated_cost":
        priced = sorted(
            (r for r in rows if r.estimated_cost is not None),
            key=lambda r: r.estimated_cost,
            reverse=reverse,
        )
        return priced + [r for r in rows if r.estimated_cost is None]
    if sort in _TOKEN_FIELDS:
        return sorted(rows, key=attrgetter(sort), reverse=reverse)
    return sorted(rows, key=attrgetter("request_count"), reverse=reverse)


class OverviewTotals(BaseModel):
    """Window+source-filtered grand totals for the table footer row (T20).

    Backend-computed, never re-summed in the client: the unpriced rule is a
    business decision, not arithmetic. Token buckets are upstream facts and sum
    unconditionally; the cost total always ships — unpriced models count as ¥0
    (an unfilled price reads as free), while rows keep their null cost as the
    not-priced marker. No pagination exists, and
    this is the FULL total by construction — name and shape stay "totals", not
    "page totals", so a future pager cannot bury a semantic trap here.
    """

    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None


class MetricDelta(BaseModel):
    """One metric's period-over-period figure.

    `previous` ships whenever the previous period was measured at all;
    `change_rate` additionally needs both sides present and a non-zero base —
    null means "cannot say", never "no change".
    """

    previous: float | None = None
    change_rate: float | None = None


class PeriodDelta(BaseModel):
    """环比 against the previous equal-length window (等长前移, not calendar months)."""

    request_count: MetricDelta
    estimated_cost: MetricDelta


class CreditValueCny(BaseModel):
    """List-price conversion of consumed credits, per basis (v3 third ledger).

    `plan` = subscription-equivalent rate, `pack` = add-on-pack rate; both are
    real prices answering different questions and render side by side, never
    auto-picked-low. A credit-reporting source missing the basis price nulls
    exactly that basis (half a bill would systematically understate). Money is
    the one cross-source comparable unit, so unlike the credit *counts* this
    may sum across sources (each row priced at its own source's rate).
    """

    plan: float | None = None
    pack: float | None = None


class CreditBySource(BaseModel):
    """One source's credit ledger, per source (v3 third ledger, 分源).

    Credit counts are a per-source unit: WorkBuddy's 1 credit and Qoder CN's 1
    credit convert to different CNY amounts, so summing credit numbers across
    sources is a fake ledger (the credit-side face of the no-cross-channel-
    merge red line). Cross-source comparison happens only after list-price
    conversion (`credit_value_cny`); the counts themselves stay per source.
    """

    source: str
    credits: float
    original_credits: float | None = None
    discount_credits: float | None = None


class Overview(BaseModel):
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    # One-off buyout/plan spend from the price table. Filled by the cost layer, not
    # by adapters: it is what was paid, independent of how much was consumed, so it
    # never joins `estimated_cost` and is never gated by the unpriced-model rule.
    # Null means the price table has no buyout row at all — "never filled" must stay
    # distinguishable from a deliberate ¥0 purchase (AGENTS.md: 没填≠0).
    buyout_total: float | None = None
    # cache_read / (input + cache_read + cache_creation) over the merged totals;
    # the denominator is all prompt tokens (方案 A, 分母含缓存写). 0 -> None.
    cache_hit_rate: float | None = None
    # 环比 vs the previous equal-length window. Null unless a closed window is
    # given AND the previous window is fully inside the data range AND non-empty —
    # a missing previous period must vanish, not render as "+300%".
    delta: PeriodDelta | None = None
    totals: OverviewTotals | None = None
    # Third ledger (v3) — field discipline per ModelUsageSummary; the aggregates
    # are derived by the cost layer, never by the client (现总价 discipline).
    # Credit counts are a per-source unit (WorkBuddy's credit ≠ Qoder CN's
    # credit), so `credits`/`credit_total`/`credit_original_total`/
    # `discount_credits` carry a value only while exactly ONE source reports
    # credits in scope — with two or more they are null and the per-source
    # ledgers in `credit_by_source` take over. `credit_value_cny` (money) may
    # span sources: each row is priced at its own source's rate, with the
    # missing-basis null gate. `plan`/`pack` degrade independently.
    credits: float | None = None
    original_credits: float | None = None
    tokens_reported: bool = True
    credits_reported: bool = False
    credit_total: float | None = None
    credit_original_total: float | None = None
    discount_credits: float | None = None
    credit_value_cny: CreditValueCny | None = None
    credit_by_source: list[CreditBySource] = []
    # Row-derived per window: sources with any credits_reported row vs any
    # tokens_reported row. The complement of the latter against active sources
    # is the "未计入 token 口径" hint list.
    credit_reporting_sources: list[str] = []
    token_reporting_sources: list[str] = []
    by_model: list[ModelUsageSummary]


class SourceRef(BaseModel):
    """One registered source in the UI enumeration — including the broken ones.

    A dead source must stay visible (greyed out with its reason), not vanish:
    a missing entry reads as "never had any usage", which is a lie.
    """

    id: str
    available: bool
    error: str | None = None


class MetaInfo(BaseModel):
    source_id: str
    # Package version (zlens.__version__) so the SPA footer never hardcodes one.
    # Not source data: adapters leave it empty; the API layer stamps the real value.
    version: str = ""
    # All registered sources with their availability, stamped by the API layer the
    # same way (adapters cannot see the registry). Empty from adapters.
    sources: list[SourceRef] = []
    request_count: int
    first_request_at: datetime | None
    last_request_at: datetime | None
    generated_at: datetime
    # Channel keys (see model_key) that have no price entry yet.
    unpriced_models: list[str] = []
    # Adapter-declared traits, unioned across the selected scope: which sources
    # report credits / tokens at all. The complement of token_reporting_sources
    # against active sources is the "未计入 token 口径" hint list.
    # unpriced_credits lists credit-reporting sources with neither basis priced
    # in `credit_prices` (the credit-side analogue of unpriced_models).
    credit_reporting_sources: list[str] = []
    token_reporting_sources: list[str] = []
    unpriced_credits: list[str] = []
    # Source-provided caveat for the UI, e.g. Qoder CN's 30-day local retention
    # (`.last-cleanup` marker): the local ledger is a sliding window the vendor
    # truncates — shown as a hint, never silently ignored. Joined across parts.
    retention_hint: str | None = None


class DailyUsage(BaseModel):
    source: str
    day: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    credits: float | None = None
    original_credits: float | None = None
    tokens_reported: bool = True
    credits_reported: bool = False


class DailyModelUsage(BaseModel):
    source: str
    day: str
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    credits: float | None = None
    original_credits: float | None = None
    tokens_reported: bool = True
    credits_reported: bool = False


class DailyTrends(BaseModel):
    granularity: str = "day"  # echoed back so the client can confirm the bucket key
    days: list[DailyUsage]
    by_model: list[DailyModelUsage]


class ModelsRanking(BaseModel):
    models: list[ModelUsageSummary]


class ProjectModelUsage(BaseModel):
    source: str
    directory: str
    title: str
    provider_id: str
    model_id: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    credits: float | None = None
    original_credits: float | None = None
    tokens_reported: bool = True
    credits_reported: bool = False


class ProjectUsage(BaseModel):
    source: str
    directory: str
    title: str
    request_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    total_tokens: int
    estimated_cost: float | None = None
    credits: float | None = None
    original_credits: float | None = None
    tokens_reported: bool = True
    credits_reported: bool = False


class ProjectsReport(BaseModel):
    projects: list[ProjectUsage]


class LatencyStats(BaseModel):
    sample_count: int
    p50_ms: float
    p90_ms: float
    p99_ms: float


class PerformanceReport(BaseModel):
    # None means the column had no non-null samples on this database.
    duration_ms: LatencyStats | None
    time_to_first_token_ms: LatencyStats | None


class ErrorGroup(BaseModel):
    source: str
    error_type: str
    error_code: str | None
    request_count: int


class HealthReport(BaseModel):
    request_count: int
    requests_with_retries: int
    total_retries: int
    cancelled_by_user: int
    context_exceeded: int
    errored_requests: int
    errors: list[ErrorGroup]
