"""
Bot configuration — all values come from environment variables.
Copy .env.example to .env and fill in your keys before running.
"""
import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:
    # ── Authentication ──────────────────────────────────────────────────────
    private_key: str = field(
        default_factory=lambda: os.getenv("POLY_PRIVATE_KEY", "")
    )
    api_key: str = field(default_factory=lambda: os.getenv("POLY_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("POLY_API_SECRET", ""))
    api_passphrase: str = field(
        default_factory=lambda: os.getenv("POLY_API_PASSPHRASE", "")
    )

    # ── Network ─────────────────────────────────────────────────────────────
    # 137 = Polygon mainnet, 80002 = Amoy testnet
    chain_id: int = field(
        default_factory=lambda: int(os.getenv("CHAIN_ID", "137"))
    )
    clob_url: str = field(
        default_factory=lambda: os.getenv("CLOB_URL", "https://clob.polymarket.com")
    )
    gamma_url: str = field(
        default_factory=lambda: os.getenv(
            "GAMMA_URL", "https://gamma-api.polymarket.com"
        )
    )

    # ── Strategy ────────────────────────────────────────────────────────────
    # Choices: arbitrage | momentum | market_making | value
    strategy: str = field(
        default_factory=lambda: os.getenv("STRATEGY", "arbitrage")
    )

    # ── Risk Management ─────────────────────────────────────────────────────
    max_position_usdc: float = field(
        default_factory=lambda: float(os.getenv("MAX_POSITION_USDC", "50.0"))
    )
    max_total_exposure_usdc: float = field(
        default_factory=lambda: float(os.getenv("MAX_TOTAL_EXPOSURE_USDC", "500.0"))
    )
    daily_loss_limit_usdc: float = field(
        default_factory=lambda: float(os.getenv("DAILY_LOSS_LIMIT_USDC", "100.0"))
    )
    max_drawdown_pct: float = field(
        default_factory=lambda: float(os.getenv("MAX_DRAWDOWN_PCT", "0.15"))
    )

    # ── Market Filters ───────────────────────────────────────────────────────
    min_volume_24h: float = field(
        default_factory=lambda: float(os.getenv("MIN_VOLUME_24H", "10000.0"))
    )
    min_liquidity: float = field(
        default_factory=lambda: float(os.getenv("MIN_LIQUIDITY", "1000.0"))
    )
    # Comma-separated list — empty means all categories
    categories: List[str] = field(
        default_factory=lambda: (
            [c.strip() for c in os.getenv("CATEGORIES", "").split(",") if c.strip()]
        )
    )

    # ── Bot Behavior ─────────────────────────────────────────────────────────
    poll_interval: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL", "30"))
    )
    # DRY_RUN=true logs orders without submitting them — use this first!
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "true").lower() == "true"
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
    log_file: str = field(
        default_factory=lambda: os.getenv("LOG_FILE", "polymarket_bot.log")
    )

    # ── Market-Making Parameters ─────────────────────────────────────────────
    mm_spread_pct: float = field(
        default_factory=lambda: float(os.getenv("MM_SPREAD_PCT", "0.02"))
    )
    mm_order_size_usdc: float = field(
        default_factory=lambda: float(os.getenv("MM_ORDER_SIZE_USDC", "10.0"))
    )
    mm_max_inventory_usdc: float = field(
        default_factory=lambda: float(os.getenv("MM_MAX_INVENTORY_USDC", "200.0"))
    )
    mm_stale_order_seconds: int = field(
        default_factory=lambda: int(os.getenv("MM_STALE_ORDER_SECONDS", "120"))
    )

    # ── Arbitrage Parameters ──────────────────────────────────────────────────
    arb_min_profit_pct: float = field(
        default_factory=lambda: float(os.getenv("ARB_MIN_PROFIT_PCT", "0.02"))
    )
    arb_max_slippage: float = field(
        default_factory=lambda: float(os.getenv("ARB_MAX_SLIPPAGE", "0.01"))
    )

    # ── Momentum Parameters ───────────────────────────────────────────────────
    momentum_lookback: int = field(
        default_factory=lambda: int(os.getenv("MOMENTUM_LOOKBACK", "10"))
    )
    momentum_threshold: float = field(
        default_factory=lambda: float(os.getenv("MOMENTUM_THRESHOLD", "0.05"))
    )

    def validate(self):
        if not self.private_key:
            raise ValueError("POLY_PRIVATE_KEY is required")
        valid_strategies = ("arbitrage", "momentum", "market_making", "value")
        if self.strategy not in valid_strategies:
            raise ValueError(
                f"Invalid STRATEGY '{self.strategy}'. Choose from: {valid_strategies}"
            )
        if self.max_position_usdc <= 0:
            raise ValueError("MAX_POSITION_USDC must be positive")


config = Config()
