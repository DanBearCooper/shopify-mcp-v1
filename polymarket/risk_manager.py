"""
Risk manager — enforces position limits, daily loss limits, and max drawdown.
All guardrails are checked here before any order reaches the exchange.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List

from .config import config
from .strategies import TradeSignal

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    daily_pnl: float = 0.0
    daily_loss: float = 0.0
    total_exposure: float = 0.0
    peak_balance: float = 0.0
    current_balance: float = 0.0
    trade_count: int = 0
    rejected_count: int = 0
    last_reset: date = field(default_factory=date.today)
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(self):
        self.state = RiskState()
        self._market_exposure: Dict[str, float] = {}  # market_id → USDC

    # ── Balance / P&L tracking ───────────────────────────────────────────────

    def update_balance(self, balance: float):
        self.state.current_balance = balance
        if balance > self.state.peak_balance:
            self.state.peak_balance = balance

    def record_pnl(self, delta_usdc: float):
        self._maybe_reset_daily()
        self.state.daily_pnl += delta_usdc
        if delta_usdc < 0:
            self.state.daily_loss += abs(delta_usdc)

    def _maybe_reset_daily(self):
        today = date.today()
        if today != self.state.last_reset:
            logger.info(
                f"New trading day — daily P&L reset "
                f"(yesterday: {self.state.daily_pnl:+.2f} USDC, "
                f"loss: {self.state.daily_loss:.2f} USDC)"
            )
            self.state.daily_pnl = 0.0
            self.state.daily_loss = 0.0
            self.state.trade_count = 0
            self.state.rejected_count = 0
            self.state.last_reset = today

    # ── Exposure tracking ────────────────────────────────────────────────────

    def open_position(self, market_id: str, size_usdc: float):
        self._market_exposure[market_id] = (
            self._market_exposure.get(market_id, 0.0) + size_usdc
        )
        self._recompute_exposure()

    def close_position(self, market_id: str, size_usdc: float):
        current = self._market_exposure.get(market_id, 0.0)
        self._market_exposure[market_id] = max(0.0, current - size_usdc)
        self._recompute_exposure()

    def _recompute_exposure(self):
        self.state.total_exposure = sum(self._market_exposure.values())

    def market_exposure(self, market_id: str) -> float:
        return self._market_exposure.get(market_id, 0.0)

    # ── Drawdown ─────────────────────────────────────────────────────────────

    @property
    def drawdown(self) -> float:
        if self.state.peak_balance <= 0:
            return 0.0
        return (self.state.peak_balance - self.state.current_balance) / self.state.peak_balance

    # ── Circuit breakers ─────────────────────────────────────────────────────

    def check_circuit_breakers(self) -> bool:
        self._maybe_reset_daily()

        if self.state.halted:
            logger.warning(f"Bot is HALTED: {self.state.halt_reason}")
            return False

        if self.state.daily_loss >= config.daily_loss_limit_usdc:
            self._halt(
                f"Daily loss limit: {self.state.daily_loss:.2f} USDC "
                f">= {config.daily_loss_limit_usdc:.2f} USDC"
            )
            return False

        if self.drawdown >= config.max_drawdown_pct:
            self._halt(
                f"Max drawdown: {self.drawdown*100:.1f}% "
                f">= {config.max_drawdown_pct*100:.1f}%"
            )
            return False

        return True

    def _halt(self, reason: str):
        self.state.halted = True
        self.state.halt_reason = reason
        logger.critical(f"⛔ CIRCUIT BREAKER TRIPPED — {reason}")

    def resume(self):
        """Manually resume after investigating a halt."""
        self.state.halted = False
        self.state.halt_reason = ""
        logger.info("Bot RESUMED — circuit breaker cleared manually")

    # ── Signal filtering ─────────────────────────────────────────────────────

    def filter_signals(self, signals: List[TradeSignal]) -> List[TradeSignal]:
        approved: List[TradeSignal] = []

        for signal in signals:
            mkt_exp = self.market_exposure(signal.market_id)

            # Per-market cap
            if mkt_exp + signal.size_usdc > config.max_position_usdc:
                logger.debug(
                    f"Rejected (per-market cap): {signal.market_id[:12]} "
                    f"exposure {mkt_exp + signal.size_usdc:.2f} > {config.max_position_usdc:.2f}"
                )
                self.state.rejected_count += 1
                continue

            # Global exposure cap
            if self.state.total_exposure + signal.size_usdc > config.max_total_exposure_usdc:
                logger.warning(
                    f"Global exposure cap reached ({self.state.total_exposure:.2f} USDC)"
                )
                self.state.rejected_count += 1
                break

            # Minimum confidence filter
            if signal.confidence < 0.3:
                logger.debug(
                    f"Rejected (low confidence={signal.confidence:.2f}): {signal.reason}"
                )
                self.state.rejected_count += 1
                continue

            approved.append(signal)

        return approved

    # ── Status ───────────────────────────────────────────────────────────────

    def status_line(self) -> str:
        status = "HALTED" if self.state.halted else "Active"
        return (
            f"[{status}] "
            f"Balance={self.state.current_balance:.2f} USDC | "
            f"Exposure={self.state.total_exposure:.2f} USDC | "
            f"DayPnL={self.state.daily_pnl:+.2f} USDC | "
            f"Drawdown={self.drawdown*100:.1f}% | "
            f"Trades={self.state.trade_count} | "
            f"Rejected={self.state.rejected_count}"
        )
