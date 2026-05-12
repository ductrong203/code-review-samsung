FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRG_GRAPH_BASE=/data/graphs \
    CRG_CLEANUP_AFTER_REVIEW=true \
    CRG_KEEP_PR_GRAPH=false \
    CRG_KEEP_FAILED_PR_GRAPH=false \
    CRG_MAX_CACHE_SIZE_GB=10 \
    CRG_MAX_PR_GRAPH_AGE_HOURS=24 \
    REVIEW_SERVER_URL=http://backend:8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY extension/requirements.txt ./extension/requirements.txt
RUN pip install --no-cache-dir -r ./extension/requirements.txt

COPY backend ./backend
COPY extension ./extension

RUN mkdir -p /data/graphs /repos

WORKDIR /app/extension

EXPOSE 8100

CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8100"]
