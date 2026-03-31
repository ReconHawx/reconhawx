# Build gotator in an isolated stage so the runtime image does not ship the Go toolchain
# (avoids a large class of golang/stdlib CVEs in production scans).
FROM golang:1.24-bookworm AS gotator-builder
RUN go install github.com/Josue87/gotator@latest

FROM python:3.14-slim

RUN apt update && \
    apt upgrade -y && \
    apt install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

COPY --from=gotator-builder /go/bin/gotator /usr/local/bin/gotator

COPY ./ .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

ENV PYTHONUNBUFFERED=1

ENV LOG_LEVEL=DEBUG
ENTRYPOINT ["/entrypoint.sh"]
