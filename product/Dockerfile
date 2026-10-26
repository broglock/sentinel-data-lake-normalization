# LevelBlue Lake Hunt: web UI, REST API and MCP server.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LAKEHUNT_DATA_DIR=/data LAKEHUNT_MODE=demo LAKEHUNT_AUTH=none
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 -m lakehunt && mkdir -p /data && chown lakehunt /data
COPY app ./app
USER lakehunt
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
