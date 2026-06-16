FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polymarket/ ./polymarket/
COPY run_bot.py .

RUN useradd --create-home --shell /usr/sbin/nologin bot \
    && mkdir -p /app/logs \
    && chown -R bot:bot /app
USER bot

ENV DRY_RUN=true \
    LOG_LEVEL=INFO \
    LOG_FILE=/app/logs/polymarket_bot.log \
    POLL_INTERVAL=30

CMD ["python", "run_bot.py"]
