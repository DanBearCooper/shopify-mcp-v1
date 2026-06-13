"""
Momentum strategy.

Looks at recent price history for each market.  If the YES-token has moved
strongly in one direction over the lookback window, we follow that trend:
  - Strong upward move  → buy YES
  - Strong downward move → buy NO (equivalent to shorting YES)

Avoids markets already near certainty (>85% or <15%) to limit tail risk.
"""
import logging
from typing import List, Dict, Optional

from py_clob_client.order_builder.constants import BUY

from .base import BaseStrategy, TradeSignal
from ..config import config

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def analyze(self, markets: List[Dict]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        for market in markets:
            tokens = market.get("tokens") or []
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
            if not yes_token:
                continue

            cid = market["condition_id"]
            history = self.client.get_price_history(cid, interval="1d")
            if len(history) < config.momentum_lookback:
                continue

            recent = history[-config.momentum_lookback :]
            prices = [float(p.get("p", 0)) for p in recent if p.get("p")]
            if len(prices) < 2 or prices[0] == 0:
                continue

            current = prices[-1]
            change = (current - prices[0]) / prices[0]

            if abs(change) < config.momentum_threshold:
                continue

            question = market.get("question", cid)[:80]
            logger.info(
                f"MOMENTUM | {question} | "
                f"change={change*100:+.1f}% current={current:.3f}"
            )

            size = min(
                config.max_position_usdc * min(abs(change) / 0.15, 1.0),
                config.max_position_usdc,
            )
            confidence = min(abs(change) / 0.2, 1.0)

            if change > config.momentum_threshold and current < 0.88:
                # Upward momentum → buy YES
                mid = self.client.get_midpoint(yes_token["token_id"])
                if mid and mid < 0.88:
                    signals.append(
                        TradeSignal(
                            market_id=cid,
                            token_id=yes_token["token_id"],
                            side=BUY,
                            size_usdc=size,
                            price=round(mid * (1 + config.arb_max_slippage), 4),
                            order_type="limit",
                            reason=f"Momentum UP {change*100:+.1f}% over {config.momentum_lookback}d",
                            confidence=confidence,
                        )
                    )

            elif change < -config.momentum_threshold and current > 0.12 and no_token:
                # Downward YES momentum → buy NO
                no_mid = self.client.get_midpoint(no_token["token_id"])
                if no_mid and no_mid < 0.88:
                    signals.append(
                        TradeSignal(
                            market_id=cid,
                            token_id=no_token["token_id"],
                            side=BUY,
                            size_usdc=size,
                            price=round(no_mid * (1 + config.arb_max_slippage), 4),
                            order_type="limit",
                            reason=f"Momentum DOWN {change*100:+.1f}% over {config.momentum_lookback}d, buying NO",
                            confidence=confidence,
                        )
                    )

        return signals
