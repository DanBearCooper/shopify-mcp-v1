#!/usr/bin/env python3
"""
Entry point for the Polymarket Auto Trading Bot.

    python run_bot.py

Configure via polymarket/.env (copy from polymarket/.env.example).
"""
import asyncio
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(__file__))

from polymarket.bot import PolymarketBot


def main():
    bot = PolymarketBot()
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
