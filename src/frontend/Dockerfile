# Build stage
FROM node:20-alpine AS build

RUN apk update && apk upgrade --no-cache

WORKDIR /app

# Copy package files
COPY package*.json ./

RUN npm install

COPY . .

ARG REACT_APP_GITHUB_RELEASES_REPO=ReconHawx/reconhawx
ENV REACT_APP_GITHUB_RELEASES_REPO=$REACT_APP_GITHUB_RELEASES_REPO

# Optional: Grafana origin for “Runner / Worker pod logs” links on workflow run pages (see kubernetes/observability/).
ARG REACT_APP_GRAFANA_URL=
ENV REACT_APP_GRAFANA_URL=$REACT_APP_GRAFANA_URL

RUN npm run build

# Slim variant: full nginx:alpine adds image-filter (libavif, libtiff) and curl.
FROM nginx:stable-alpine-slim

RUN apk update && apk upgrade --no-cache

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY --from=build /app/build /usr/share/nginx/html

# Serve GET /status via nginx (see frontend-nginx-config); bake semver into JSON
RUN printf '{"status":"healthy","service":"frontend","version":"%s","checks":{"static":{"status":"ok"}}}\n' "$APP_VERSION" > /usr/share/nginx/html/status.json

EXPOSE 80
