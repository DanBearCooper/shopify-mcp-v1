"""
Main bot loop.  Initializes the client, selects the strategy, and runs
continuous trading cycles separated by POLL_INTERVAL seconds.

Usage:
    python run_bot.py                  # uses config from .env
    DRY_RUN=false python run_bot.py    # live trading (be careful!)
"""
import asyncio
import logging
import signal as _signal
import sys
from typing import List, Dict

from .client import PolymarketClient
from .config import config
from .logger import setup_logging
from .order_manager import OrderManager
from .risk_manager import RiskManager
from .strategies import get_strategy

logger = logging.getLogger(__name__)


class PolymarketBot:
    def __init__(self):
        self.client = PolymarketClient()
        self.risk = RiskManager()
        self.order_mgr = OrderManager(self.client, self.risk)
        self.strategy = get_strategy(config.strategy, self.client)
        self._running = False
        self._cycle = 0

    # ── Startup ──────────────────────────────────────────────────────────────

    def initialize(self):
        setup_logging(config.log_level, config.log_file)
        logger.info("=" * 60)
        logger.info(
            f"Polymarket Auto Bot | Strategy: {config.strategy} | "
            f"DryRun: {config.dry_run} | ChainID: {config.chain_id}"
        )
        logger.info("=" * 60)

        try:
            config.validate()
        except ValueError as exc:
            logger.critical(f"Config error: {exc}")
            sys.exit(1)

        self.client.initialize()
        balance = self.client.get_balance()
        self.risk.update_balance(balance)
        logger.info(f"Wallet balance: {balance:.4f} USDC")

        if config.dry_run:
            logger.warning(
                "DRY RUN enabled — no real orders will be placed. "
                "Set DRY_RUN=false in .env when ready."
            )

    # ── Market fetching ───────────────────────────────────────────────────────

    def fetch_active_markets(self) -> List[Dict]:
        all_markets = self.client.get_all_markets()
        filtered: List[Dict] = []

        for m in all_markets:
            if m.get("closed") or m.get("archived"):
                continue

            vol = float(m.get("volume", 0) or 0)
            if vol < config.min_volume_24h:
                continue

            # Optional category filter
            if config.categories:
                tags = [
                    t.get("label", "").lower()
                    for t in (m.get("tags") or [])
                ]
                if not any(cat.lower() in tags for cat in config.categories):
                    continue

            filtered.append(m)

        logger.info(
            f"Markets: {len(filtered)} active "
            f"(from {len(all_markets)} total, vol≥{config.min_volume_24h:.0f})"
        )
        return filtered

    # ── Trading cycle ─────────────────────────────────────────────────────────

    async def run_cycle(self):
        self._cycle += 1
        logger.info(f"── Cycle {self._cycle} ──────────────────────────────────")

        # Circuit breaker check
        if not self.risk.check_circuit_breakers():
            return

        # Sync order state and cancel stale limit orders
        self.order_mgr.sync_orders()
        self.order_mgr.cancel_stale_orders(
            max_age_seconds=config.mm_stale_order_seconds
            if config.strategy == "market_making"
            else 3_600
        )

        # Update balance
        balance = self.client.get_balance()
        self.risk.update_balance(balance)

        # Fetch markets and generate signals
        markets = self.fetch_active_markets()
        if not markets:
            logger.warning("No markets returned — skipping this cycle")
            return

        signals = self.strategy.analyze(markets)
        logger.info(f"Strategy signals: {len(signals)}")

        approved = self.risk.filter_signals(signals)
        logger.info(f"Risk-approved signals: {len(approved)}/{len(signals)}")

        # Execute approved signals with a short rate-limit pause between orders
        for signal in approved:
            self.order_mgr.execute_signal(signal)
            await asyncio.sleep(0.5)

        # Status lines
        logger.info(self.risk.status_line())
        logger.info(self.order_mgr.summary())

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        self._running = True
        self.initialize()

        loop = asyncio.get_event_loop()

        def _handle_shutdown(sig, frame):
            logger.info(f"Received signal {sig.name} — shutting down…")
            self._running = False

        for sig in (_signal.SIGINT, _signal.SIGTERM):
            _signal.signal(sig, _handle_shutdown)

        logger.info(f"Bot started. Poll interval: {config.poll_interval}s")

        while self._running:
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.error(f"Unhandled error in cycle {self._cycle}: {exc}", exc_info=True)

            if self._running:
                await asyncio.sleep(config.poll_interval)

        logger.info("Shutting down — cancelling all open orders…")
        self.client.cancel_all_orders()
        logger.info("Bot stopped.")
