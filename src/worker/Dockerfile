FROM golang:1.25-bookworm AS builder

WORKDIR /app

RUN apt update && \
    apt install -y git && \
    apt install -y make gcc wget build-essential && \
    rm -rf /var/lib/apt/lists/*

ENV CGO_ENABLED=1
ENV GOBIN=/usr/local/go/bin

# Install pdtm and tools with specific architecture handling
RUN go install -v github.com/projectdiscovery/pdtm/cmd/pdtm@latest && \
    pdtm -i subfinder && \
    pdtm -i httpx && \
    pdtm -i dnsx && \
    pdtm -i katana && \
    pdtm -i nuclei

RUN go install github.com/Josue87/gotator@latest

RUN go install -v github.com/owasp-amass/amass/v4/...@master

RUN go install -v github.com/sensepost/gowitness@latest

RUN go install github.com/ffuf/ffuf/v2@latest

RUN cd /tmp && git clone https://github.com/blechschmidt/massdns --tag v1.1.0 && \
    cd /tmp/v1.1.0 && \
    make && \
    mv /tmp/v1.1.0/bin/massdns /usr/local/bin/massdns

RUN go install github.com/d3mondev/puredns/v2@latest

RUN go install github.com/lc/gau/v2/cmd/gau@latest

RUN go install github.com/tomnomnom/unfurl@latest

RUN go install github.com/tomnomnom/assetfinder@latest

RUN go install github.com/praetorian-inc/nerva/cmd/nerva@latest

## Final stage
FROM python:3.14-slim

WORKDIR /workspace

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
    git \
    jq \
    prips \
    nmap \
    wget \
    dnsutils \
    chromium \
    chromium-sandbox \
    curl \
    inetutils-ping \
    netcat-openbsd \
    pipx \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    ruby \
    ruby-dev \
    ruby-curb \
    make \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV CGO_ENABLED=1
ENV GOBIN=/usr/local/bin
    
RUN ARCH=$(dpkg --print-architecture) && \
    case ${ARCH} in \
        amd64) GOARCH="amd64" ;; \
        arm64) GOARCH="arm64" ;; \
        *) echo "Unsupported architecture: ${ARCH}" && exit 1 ;; \
    esac && \
    wget "https://go.dev/dl/go1.23.4.linux-${GOARCH}.tar.gz" -O /tmp/go.tar.gz && \
    tar -C /usr/local -xzf /tmp/go.tar.gz && \
    rm /tmp/go.tar.gz

ENV PATH="$PATH:/usr/local/go/bin:/root/.local/bin"

ENV PYTHONUNBUFFERED=1

ENV PYTHONFAULTHANDLER=1

# Set working directory
WORKDIR /workspace

COPY ./requirements.txt .

RUN pip install -r requirements.txt

# Install Playwright browsers (without --with-deps since we already installed system dependencies)
RUN playwright install chromium

RUN pipx install urless

RUN gem install wpscan

# Copy the command wrapper script and entrypoint
COPY ./command_wrapper.py /usr/local/bin/

COPY ./utils/ /workspace/utils/

COPY ./dnsx_wrapper.py .

COPY ./whois_domain_wrapper.py .

COPY ./crawl_website.py .

COPY ./screenshotter.sh .

COPY ./typosquat_worker.py .

COPY ./ffuf_wrapper.py .

COPY ./run-batch-job.py .

COPY ./check_broken_links.py .

COPY ./puredns_wrapper.py .

COPY ./port_scan_wrapper.py .

COPY files/ /workspace/files/

COPY --from=builder /usr/local/go/bin/* /usr/local/bin/

COPY --from=builder /root/.pdtm/go/bin/* /usr/local/bin/

COPY --from=builder /usr/local/bin/massdns /usr/local/bin/massdns

# Make scripts executable and create symlinks in root
RUN chmod +x /usr/local/bin/command_wrapper.py

# Nuclei configuration
RUN mkdir -p /root/.config/nuclei && \
    cp /workspace/files/nuclei.yaml /root/.config/nuclei/config.yaml

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
