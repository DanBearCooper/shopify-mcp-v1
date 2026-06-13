"""
Market-making strategy.

Places a resting bid and ask around the mid-price on both outcomes of each
binary market.  Profits from the bid-ask spread.  Works best on liquid markets
with tight natural spreads.

Stale orders are cancelled by the OrderManager; this strategy simply generates
fresh quotes each cycle.
"""
import logging
from typing import List, Dict

from py_clob_client.order_builder.constants import BUY, SELL

from .base import BaseStrategy, TradeSignal
from ..config import config

logger = logging.getLogger(__name__)

# Only make markets within this probability range — avoids near-certain outcomes
_PRICE_LO = 0.06
_PRICE_HI = 0.94


class MarketMakingStrategy(BaseStrategy):
    name = "market_making"

    def analyze(self, markets: List[Dict]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        for market in markets:
            tokens = market.get("tokens") or []
            for token in tokens:
                token_id = token["token_id"]
                mid = self.client.get_midpoint(token_id)
                if mid is None or not (_PRICE_LO <= mid <= _PRICE_HI):
                    continue

                spread = self.client.get_spread(token_id)
                if spread is None:
                    spread = 0.02

                # Our half-spread is at least mm_spread_pct/2, or existing half-spread + buffer
                half = max(config.mm_spread_pct / 2, spread / 2 + 0.005)

                bid = round(max(0.01, mid - half), 4)
                ask = round(min(0.99, mid + half), 4)

                label = token.get("outcome", token_id[:8])
                logger.debug(
                    f"MM quote | {market.get('question','?')[:50]} [{label}] "
                    f"bid={bid:.4f} ask={ask:.4f} mid={mid:.4f}"
                )

                for side, price in [(BUY, bid), (SELL, ask)]:
                    signals.append(
                        TradeSignal(
                            market_id=market["condition_id"],
                            token_id=token_id,
                            side=side,
                            size_usdc=config.mm_order_size_usdc,
                            price=price,
                            order_type="limit",
                            reason=(
                                f"MM {side} {label} @ {price:.4f} "
                                f"(mid={mid:.4f}, spread={spread:.4f})"
                            ),
                            confidence=0.55,
                        )
                    )

        return signals
