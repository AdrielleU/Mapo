FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# System deps for Playwright/Camoufox
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 libxcursor1 libasound2 libdbus-glib-1-2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install firefox

COPY . .
RUN mkdir -p data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health', timeout=5)"

CMD ["python", "run.py"]
