"""
Arbitrage strategy.

On binary Polymarket markets, YES-token + NO-token prices must sum to 1.0
after fees. When they deviate significantly, there is a risk-free (or near-
risk-free) profit: buy both sides at a combined cost < 1.0 and collect 1.0
at resolution.

A ~2% fee buffer is included because Polymarket charges a maker/taker fee.
"""
import logging
from typing import List, Dict

from py_clob_client.order_builder.constants import BUY

from .base import BaseStrategy, TradeSignal
from ..config import config

logger = logging.getLogger(__name__)

# Approximate round-trip fee on Polymarket (maker + taker each side)
_FEE_BUFFER = 0.04


class ArbitrageStrategy(BaseStrategy):
    name = "arbitrage"

    def analyze(self, markets: List[Dict]) -> List[TradeSignal]:
        signals: List[TradeSignal] = []

        for market in markets:
            tokens = market.get("tokens") or []
            if len(tokens) < 2:
                continue

            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
            if not yes_token or not no_token:
                continue

            yes_mid = self.client.get_midpoint(yes_token["token_id"])
            no_mid = self.client.get_midpoint(no_token["token_id"])

            if yes_mid is None or no_mid is None or yes_mid <= 0 or no_mid <= 0:
                continue

            total = yes_mid + no_mid
            edge = 1.0 - total - _FEE_BUFFER  # net profit after fees

            if edge < config.arb_min_profit_pct:
                continue

            question = market.get("question", market.get("condition_id", "?"))[:80]
            profit_pct = edge * 100
            logger.info(
                f"ARB OPPORTUNITY | {question} | "
                f"YES={yes_mid:.3f} NO={no_mid:.3f} total={total:.3f} "
                f"edge={profit_pct:.2f}%"
            )

            # Size each leg at half of max_position so total exposure = max_position
            leg_size = min(config.max_position_usdc / 2, 25.0)

            for token, label in [(yes_token, "YES"), (no_token, "NO")]:
                signals.append(
                    TradeSignal(
                        market_id=market["condition_id"],
                        token_id=token["token_id"],
                        side=BUY,
                        size_usdc=leg_size,
                        price=None,
                        order_type="market",
                        reason=(
                            f"Arb: {label} leg | total={total:.3f} "
                            f"edge={profit_pct:.2f}%"
                        ),
                        confidence=min(edge / 0.1, 1.0),
                    )
                )

        return signals
