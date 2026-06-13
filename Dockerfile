FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polymarket/ ./polymarket/
COPY run_bot.py .

ENV DRY_RUN=true \
    LOG_LEVEL=INFO \
    POLL_INTERVAL=30

CMD ["python", "run_bot.py"]
