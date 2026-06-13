"""
Order lifecycle management: execution, tracking, sync, and cancellation.
All order state is held in-memory; a SQLite backend could be added for
persistence across restarts.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .client import PolymarketClient
from .risk_manager import RiskManager
from .strategies import TradeSignal

logger = logging.getLogger(__name__)


@dataclass
class Order:
    order_id: str
    market_id: str
    token_id: str
    side: str
    size_usdc: float
    price: Optional[float]
    order_type: str
    status: str = "open"        # open | filled | cancelled | failed
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    reason: str = ""


class OrderManager:
    def __init__(self, client: PolymarketClient, risk: RiskManager):
        self.client = client
        self.risk = risk
        self._orders: Dict[str, Order] = {}

    # ── Execution ────────────────────────────────────────────────────────────

    def execute_signal(self, signal: TradeSignal) -> Optional[Order]:
        price_str = "MKT" if signal.price is None else f"{signal.price:.4f}"
        logger.info(
            f"Executing {signal.side} {signal.size_usdc:.2f} USDC "
            f"@ {price_str} on {signal.token_id[:12]}… | {signal.reason}"
        )

        if signal.order_type == "market":
            result = self.client.create_market_order(
                token_id=signal.token_id,
                side=signal.side,
                size=signal.size_usdc,
            )
        else:
            result = self.client.create_limit_order(
                token_id=signal.token_id,
                side=signal.side,
                price=signal.price,
                size=signal.size_usdc,
            )

        if not result:
            logger.error(f"Order execution returned None for: {signal.reason}")
            self._record(signal, status="failed", order_id=f"fail_{int(time.time())}")
            return None

        order_id = (
            result.get("orderID")
            or result.get("id")
            or result.get("order_id")
            or f"dry_{signal.token_id[:8]}_{int(time.time())}"
        )
        status = result.get("status", "open")
        if status == "dry_run":
            status = "open"

        order = Order(
            order_id=order_id,
            market_id=signal.market_id,
            token_id=signal.token_id,
            side=signal.side,
            size_usdc=signal.size_usdc,
            price=signal.price,
            order_type=signal.order_type,
            status=status,
            reason=signal.reason,
        )
        self._orders[order_id] = order
        self.risk.open_position(signal.market_id, signal.size_usdc)
        self.risk.state.trade_count += 1
        return order

    def _record(self, signal: TradeSignal, status: str, order_id: str) -> Order:
        order = Order(
            order_id=order_id,
            market_id=signal.market_id,
            token_id=signal.token_id,
            side=signal.side,
            size_usdc=signal.size_usdc,
            price=signal.price,
            order_type=signal.order_type,
            status=status,
            reason=signal.reason,
        )
        self._orders[order_id] = order
        return order

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def sync_orders(self):
        """Fetch current open orders from exchange and mark filled orders."""
        live_orders = self.client.get_open_orders()
        live_ids = {o.get("id") or o.get("orderID") for o in live_orders}

        for oid, order in list(self._orders.items()):
            if order.status != "open":
                continue
            if oid.startswith("dry_"):
                continue  # dry-run orders are never filled via exchange
            if oid not in live_ids:
                order.status = "filled"
                order.filled_at = datetime.now(timezone.utc)
                self.risk.close_position(order.market_id, order.size_usdc)
                logger.info(f"Order filled: {oid}")

    def cancel_stale_orders(self, max_age_seconds: int = 300):
        """Cancel limit orders that have been open too long without filling."""
        now = datetime.now(timezone.utc)
        for oid, order in list(self._orders.items()):
            if order.status != "open" or order.order_type == "market":
                continue
            age = (now - order.created_at).total_seconds()
            if age > max_age_seconds:
                if self.client.cancel_order(oid):
                    order.status = "cancelled"
                    self.risk.close_position(order.market_id, order.size_usdc)
                    logger.info(f"Cancelled stale order {oid} (age={age:.0f}s)")

    # ── Queries ──────────────────────────────────────────────────────────────

    def active_orders(self) -> List[Order]:
        return [o for o in self._orders.values() if o.status == "open"]

    def filled_orders(self) -> List[Order]:
        return [o for o in self._orders.values() if o.status == "filled"]

    def summary(self) -> str:
        active = len(self.active_orders())
        filled = len(self.filled_orders())
        cancelled = sum(1 for o in self._orders.values() if o.status == "cancelled")
        return (
            f"Orders | Active={active} Filled={filled} "
            f"Cancelled={cancelled} Total={len(self._orders)}"
        )
