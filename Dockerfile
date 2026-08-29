# syntax=docker/dockerfile:1

ARG QUERY_DOCTOR_PYTHON_BASE_IMAGE=python:3.13-slim

FROM ${QUERY_DOCTOR_PYTHON_BASE_IMAGE} AS runtime

ARG QUERY_DOCTOR_INSTALL_EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUERY_DOCTOR_CONTAINER=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt/query-doctor

# krb5-user carries klist, which the metadata Kerberos preflight runs, and
# libkrb5-3, which pykerberos links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        krb5-user \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 querydoctor \
    && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin querydoctor

COPY pyproject.toml setup.py README.md LICENSE ./
COPY query_doctor ./query_doctor

# pykerberos, which the impala extra pulls in for the GSSAPI handshake, ships no
# wheel. The toolchain and the Kerberos headers are installed and removed inside
# one layer so they do not reach the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libkrb5-dev \
    && /usr/local/bin/python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && if [ -n "${QUERY_DOCTOR_INSTALL_EXTRAS}" ]; then \
        /usr/local/bin/python -m pip install --no-cache-dir ".[${QUERY_DOCTOR_INSTALL_EXTRAS}]"; \
    else \
        /usr/local/bin/python -m pip install --no-cache-dir --no-deps .; \
    fi \
    && apt-get purge -y --auto-remove gcc libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*

USER 10001:10001

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/healthz', timeout=3).read()"

ENTRYPOINT ["query-doctor-web"]
CMD ["--host", "0.0.0.0", "--port", "8765", "--allow-nonlocal-web-bind", "--public-demo"]
