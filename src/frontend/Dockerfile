# Build stage
FROM node:20-alpine AS build

RUN apk update && apk upgrade --no-cache

WORKDIR /app

# Copy package files
COPY package*.json ./

RUN npm install

COPY . .

RUN npm run build

# Slim variant: full nginx:alpine adds image-filter (libavif, libtiff) and curl.
FROM nginx:stable-alpine-slim

RUN apk update && apk upgrade --no-cache

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
