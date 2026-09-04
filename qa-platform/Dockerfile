# QA platform — FastAPI runner + Playwright/Chromium
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- python deps -------------------------------------------------------
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

# --- Chromium + its OS libraries ---------------------------------------
# --with-deps installs the apt packages Chromium needs (fonts, nss, X libs).
# Baked into the image so no browser download happens at run time.
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
EXPOSE 7000

# Bind outside the container; the port itself comes from
# config/local.yaml (RUNNER_PORT), which config.py loads at import.
ENV RUNNER_HOST=0.0.0.0

CMD ["python", "run_server.py"]
