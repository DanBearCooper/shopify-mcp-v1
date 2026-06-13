from .base import BaseStrategy, TradeSignal
from .arbitrage import ArbitrageStrategy
from .momentum import MomentumStrategy
from .market_making import MarketMakingStrategy
from .value import ValueStrategy

STRATEGIES = {
    "arbitrage": ArbitrageStrategy,
    "momentum": MomentumStrategy,
    "market_making": MarketMakingStrategy,
    "value": ValueStrategy,
}


def get_strategy(name: str, client) -> BaseStrategy:
    cls = STRATEGIES.get(name)
    if not cls:
        raise ValueError(
            f"Unknown strategy '{name}'. Choose from: {list(STRATEGIES)}"
        )
    return cls(client)
