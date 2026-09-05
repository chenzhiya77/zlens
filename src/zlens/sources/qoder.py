"""International Qoder CLI adapter (v3 T37).

Same transcript shape and credit metering as the CN CLI (QoderCnSource) with a
different root (``~/.qoder``) and a separate source id — the two products'
credits are priced differently and are not interchangeable, so they never share
a ledger (per-source credit design). 取证 (2026-09-05): 483 deduped billed calls
/ Σ 1061.21 credits on the local machine, tokens structurally absent, zero
request_id overlap with ``~/.qoder-cn`` — genuinely distinct surfaces, no
double-metering risk from registering both.
"""

from pathlib import Path

from zlens.sources.qoder_cn import QoderCnSource


class QoderSource(QoderCnSource):
    id = "qoder"
    RETENTION_HINT = "Qoder CLI 会话本地保留 30 天，更早的历史已不在本地。"

    def __init__(self, config_dir: Path) -> None:
        super().__init__(config_dir)
