"""
Value / mispricing detection strategy.

Identifies markets where the crowd probability seems extreme given the time
remaining until resolution and the recent trading volume.  This is mostly a
*scanner* that logs opportunities; it can optionally emit signals when it
finds markets that look mispriced relative to a simple baseline.

Extend this class with your own external data sources (news APIs, model
probabilities, forecasting services) to turn it into a real edge.
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

from py_clob_client.order_builder.constants import BUY

from .base import BaseStrategy, TradeSignal
from ..config import config

logger = logging.getLogger(__name__)


class ValueStrategy(BaseStrategy):
    name = "value"

    def analyze(self, markets: List[Dict]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        for market in markets:
            tokens = market.get("tokens") or []
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            if not yes_token:
                continue

            mid = self.client.get_midpoint(yes_token["token_id"])
            if mid is None or mid <= 0:
                continue

            days_left = self._days_to_end(market)
            volume = float(market.get("volume", 0) or 0)
            question = market.get("question", market["condition_id"])[:80]

            # ── Log extreme prices with short time horizons ──────────────────
            if days_left is not None and days_left <= 7:
                if mid < 0.05 and volume > 5_000:
                    logger.info(
                        f"VALUE WATCH (near-zero, active) | {question} | "
                        f"p={mid:.3f} vol={volume:.0f} days={days_left:.1f}"
                    )
                elif mid > 0.95 and volume > 5_000:
                    logger.info(
                        f"VALUE WATCH (near-one, active) | {question} | "
                        f"p={mid:.3f} vol={volume:.0f} days={days_left:.1f}"
                    )

            # ── Example signal: fade extreme crowd certainty near resolution ─
            # This is a placeholder — replace with a real model/signal.
            # Uncomment and tune if you have an external probability estimate.
            #
            # my_prob = external_model_prob(market)
            # if my_prob - mid > 0.10:
            #     signals.append(TradeSignal(..., reason="Value: model says higher"))

        return signals

    def _days_to_end(self, market: Dict) -> Optional[float]:
        for key in ("end_date_iso", "endDateIso", "end_date"):
            raw = market.get(key)
            if raw:
                break
        if not raw:
            return None
        try:
            end = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            delta = end - datetime.now(timezone.utc)
            return max(delta.total_seconds() / 86_400, 0.0)
        except Exception:
            return None
