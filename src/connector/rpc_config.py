from __future__ import annotations

import os
from typing import Final


def _env_card_id(name: str) -> int | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


CARD_ID_PARTNER_REVENUE: Final[int | None] = _env_card_id("CARD_ID_PARTNER_REVENUE")
CARD_ID_CHANNEL_SPLIT: Final[int | None] = _env_card_id("CARD_ID_CHANNEL_SPLIT")
CARD_ID_TOP_PARTNERS: Final[int | None] = _env_card_id("CARD_ID_TOP_PARTNERS")
CARD_ID_MRR_TREND: Final[int | None] = _env_card_id("CARD_ID_MRR_TREND") or 159
CARD_ID_ARR_AT_RISK: Final[int | None] = _env_card_id("CARD_ID_ARR_AT_RISK")
CARD_ID_UPSELL_OPPORTUNITIES: Final[int | None] = _env_card_id("CARD_ID_UPSELL_OPPORTUNITIES")
CARD_ID_REVENUE_COMPARISON: Final[int | None] = _env_card_id("CARD_ID_REVENUE_COMPARISON")
CARD_ID_DATA_QUALITY_SIGNALS: Final[int | None] = _env_card_id("CARD_ID_DATA_QUALITY_SIGNALS")
CARD_ID_LICENSE_QUERY: Final[int | None] = _env_card_id("CARD_ID_LICENSE_QUERY")
