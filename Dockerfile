FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# System deps for both Camoufox (Firefox) AND Patchright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Firefox/Camoufox deps
    libgtk-3-0 libdbus-glib-1-2 libxt6 \
    # Chromium/Patchright deps
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 \
    # Shared deps
    libxcursor1 libasound2 libx11-6 libx11-xcb1 libxext6 libxi6 libxcb1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install firefox chromium

# Copy only what's needed (avoids .dockerignore pattern issues with backend/data/)
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
COPY mapo.yaml run.py ./

RUN mkdir -p data
RUN python scripts/generate_frontend_data.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health', timeout=5)"

CMD ["python", "run.py"]
