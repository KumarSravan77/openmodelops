FROM python:3.12-slim AS runtime
ARG SERVICE
ARG EXTRAS=""
ARG PIP_INDEX_URL="https://pypi.org/simple"
ARG PIP_TRUSTED_HOST=""
ENV PIP_INDEX_URL=${PIP_INDEX_URL} PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
ENV SERVICE=${SERVICE} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 openmodelops \
    && mkdir -p /data \
    && chown openmodelops:openmodelops /data
COPY pyproject.toml .
RUN if [ -n "$EXTRAS" ]; then pip install --no-cache-dir ".[${EXTRAS}]"; else pip install --no-cache-dir .; fi
COPY packages packages
COPY platforms platforms
COPY catalog catalog
COPY examples examples
COPY .beacode .beacode
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"
CMD ["sh", "-c", "uvicorn platforms.${SERVICE}.api:app --host 0.0.0.0 --port 8000"]
