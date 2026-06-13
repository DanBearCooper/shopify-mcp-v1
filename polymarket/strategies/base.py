from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import PolymarketClient


@dataclass
class TradeSignal:
    market_id: str
    token_id: str
    side: str              # "BUY" or "SELL"
    size_usdc: float
    price: Optional[float] # None = market order
    order_type: str        # "market" or "limit"
    reason: str
    confidence: float      # 0.0 – 1.0


class BaseStrategy(ABC):
    def __init__(self, client: "PolymarketClient"):
        self.client = client

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def analyze(self, markets: List[dict]) -> List[TradeSignal]:
        """Return a list of trade signals for the given set of active markets."""
        ...
