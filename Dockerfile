FROM chetan1111/botasaurus:latest

ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Install optional deps if needed (uncomment as required)
# RUN pip install --no-cache-dir psycopg2-binary gspread google-auth boto3
# RUN pip install --no-cache-dir anthropic openai

COPY . /app

RUN python run.py install

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health', timeout=5)" || exit 1

CMD ["python", "run.py"]
