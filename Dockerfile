# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
WORKDIR /app
# Optional mounted CA bundle supports managed build proxies without embedding session trust.
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99-vivi-build-ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends ffmpeg libopus0 ca-certificates \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-vivi-build-ca
COPY requirements.txt ./
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 vivi && useradd --uid 10001 --gid vivi --create-home vivi
COPY --chown=vivi:vivi . .
RUN mkdir -p /app/data && chown vivi:vivi /app/data
USER vivi
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD ["python", "-m", "vivi.healthcheck"]
CMD ["python", "-m", "vivi.supervisor"]
