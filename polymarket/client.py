"""
Thin wrapper around py-clob-client that adds retry logic, logging,
and dry-run support. All raw CLOB API calls live here.
"""
import logging
import time
from typing import Dict, List, Optional, Any

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from .config import config

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 2.0  # seconds


def _with_retry(fn, *args, **kwargs):
    last_exc = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                wait = _RETRY_BACKOFF * (attempt + 1)
                logger.warning(f"Retry {attempt + 1}/{_RETRY_ATTEMPTS} after error: {exc}. Waiting {wait}s")
                time.sleep(wait)
    logger.error(f"All {_RETRY_ATTEMPTS} attempts failed: {last_exc}")
    return None


class PolymarketClient:
    def __init__(self):
        creds = (
            ApiCreds(
                api_key=config.api_key,
                api_secret=config.api_secret,
                api_passphrase=config.api_passphrase,
            )
            if config.api_key
            else None
        )
        self.clob = ClobClient(
            host=config.clob_url,
            chain_id=config.chain_id,
            key=config.private_key,
            creds=creds,
        )

    def initialize(self):
        """Create or derive API credentials from private key if not provided.

        create_or_derive_api_creds() creates new creds on first run for this
        wallet, or derives the existing ones on subsequent runs — derive_api_key()
        alone fails with no creds ever created before.
        """
        if not config.api_key:
            logger.info("Creating/deriving L2 API credentials from private key…")
            creds = _with_retry(self.clob.create_or_derive_api_creds)
            if creds:
                config.api_key = creds.api_key
                config.api_secret = creds.api_secret
                config.api_passphrase = creds.api_passphrase
                self.clob = ClobClient(
                    host=config.clob_url,
                    chain_id=config.chain_id,
                    key=config.private_key,
                    creds=creds,
                )
                logger.info(f"API credentials ready: {creds.api_key[:8]}…")
                logger.info(
                    "Save these to .env to skip re-derivation next run: "
                    f"POLY_API_KEY={creds.api_key} POLY_API_SECRET={creds.api_secret} "
                    f"POLY_API_PASSPHRASE={creds.api_passphrase}"
                )
            else:
                logger.warning("Could not create/derive API key — order placement will fail")
        else:
            logger.info(f"Using existing API key: {config.api_key[:8]}…")

    # ── Market Data ─────────────────────────────────────────────────────────

    def get_markets(self, next_cursor: str = "") -> Dict:
        result = _with_retry(self.clob.get_markets, next_cursor=next_cursor)
        return result or {"data": [], "next_cursor": "LTE="}

    def get_all_markets(self) -> List[Dict]:
        markets: List[Dict] = []
        cursor = ""
        while True:
            result = self.get_markets(next_cursor=cursor)
            batch = result.get("data") or []
            markets.extend(batch)
            cursor = result.get("next_cursor", "LTE=")
            if cursor == "LTE=":
                break
        return markets

    def get_market(self, condition_id: str) -> Optional[Dict]:
        return _with_retry(self.clob.get_market, condition_id)

    def get_orderbook(self, token_id: str) -> Optional[Dict]:
        book = _with_retry(self.clob.get_order_book, token_id)
        if book and hasattr(book, "__dict__"):
            book = book.__dict__
        return book

    def get_best_bid_ask(self, token_id: str) -> tuple[Optional[float], Optional[float]]:
        book = self.get_orderbook(token_id)
        if not book:
            return None, None
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        best_bid = float(bids[0]["price"]) if bids else None
        best_ask = float(asks[0]["price"]) if asks else None
        return best_bid, best_ask

    def get_midpoint(self, token_id: str) -> Optional[float]:
        result = _with_retry(self.clob.get_midpoint, token_id)
        if result is None:
            return None
        if isinstance(result, dict):
            return float(result.get("mid", 0)) or None
        return float(result) if result else None

    def get_spread(self, token_id: str) -> Optional[float]:
        bid, ask = self.get_best_bid_ask(token_id)
        if bid is None or ask is None:
            return None
        return round(ask - bid, 4)

    def get_price(self, token_id: str, side: str, size: float) -> Optional[float]:
        result = _with_retry(self.clob.get_price, token_id, side, size)
        if result is None:
            return None
        if isinstance(result, dict):
            return float(result.get("price", 0)) or None
        return float(result) if result else None

    def get_last_trade_price(self, token_id: str) -> Optional[float]:
        result = _with_retry(self.clob.get_last_trade_price, token_id)
        if not result:
            return None
        if isinstance(result, dict):
            return float(result.get("price", 0)) or None
        return float(result) if result else None

    def get_price_history(
        self, market_id: str, interval: str = "1d", fidelity: int = 1
    ) -> List[Dict]:
        result = _with_retry(
            self.clob.get_prices_history,
            params={"market": market_id, "interval": interval, "fidelity": fidelity},
        )
        return result or []

    # ── Account ─────────────────────────────────────────────────────────────

    def get_balance(self) -> float:
        result = _with_retry(self.clob.get_balance_allowance)
        if not result:
            return 0.0
        if isinstance(result, dict):
            return float(result.get("balance", result.get("allowance", 0)))
        return float(result)

    def get_open_orders(self, market: Optional[str] = None) -> List[Dict]:
        params: Dict[str, Any] = {}
        if market:
            params["market"] = market
        result = _with_retry(self.clob.get_orders, params)
        return result or []

    def get_positions(self) -> List[Dict]:
        result = _with_retry(self.clob.get_positions)
        return result or []

    def get_trades(self, market: Optional[str] = None) -> List[Dict]:
        params: Dict[str, Any] = {}
        if market:
            params["market"] = market
        result = _with_retry(self.clob.get_trades, params)
        return result or []

    # ── Order Execution ──────────────────────────────────────────────────────

    def create_market_order(
        self, token_id: str, side: str, size: float
    ) -> Optional[Dict]:
        if config.dry_run:
            logger.info(
                f"[DRY RUN] MARKET {side} {size:.2f} USDC on {token_id[:12]}…"
            )
            return {"orderID": f"dry_{token_id[:8]}_{int(time.time())}", "status": "dry_run"}

        order_args = OrderArgs(price=1.0 if side == BUY else 0.0, size=size, side=side, token_id=token_id)
        signed = _with_retry(self.clob.create_market_order, order_args)
        if not signed:
            return None
        result = _with_retry(self.clob.post_order, signed, OrderType.FOK)
        if result:
            logger.info(f"Market order placed: {result}")
        return result

    def create_limit_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> Optional[Dict]:
        if config.dry_run:
            logger.info(
                f"[DRY RUN] LIMIT {side} {size:.2f} USDC @ {price:.4f} on {token_id[:12]}…"
            )
            return {"orderID": f"dry_{token_id[:8]}_{int(time.time())}", "status": "dry_run"}

        order_args = OrderArgs(price=price, size=size, side=side, token_id=token_id)
        signed = _with_retry(self.clob.create_order, order_args)
        if not signed:
            return None
        result = _with_retry(self.clob.post_order, signed, OrderType.GTC)
        if result:
            logger.info(f"Limit order placed: {result}")
        return result

    def cancel_order(self, order_id: str) -> bool:
        if config.dry_run:
            logger.info(f"[DRY RUN] Cancel order {order_id}")
            return True
        result = _with_retry(self.clob.cancel, order_id)
        return result is not None

    def cancel_all_orders(self) -> bool:
        if config.dry_run:
            logger.info("[DRY RUN] Cancel all orders")
            return True
        result = _with_retry(self.clob.cancel_all)
        return result is not None
