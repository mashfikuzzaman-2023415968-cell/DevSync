# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
# Edge image: unprivileged Nginx + brotli dynamic modules + the production SPA build.
# Build context: repository root.
# Stable line on Debian trixie (bookworm images are no longer rebuilt; DECISIONS D18).
ARG NGINX_VERSION=1.30.4
# Digest of nginxinc/nginx-unprivileged:1.30.4-trixie (2026-09-14); change it with NGINX_VERSION.
ARG NGINX_RUNTIME_DIGEST=sha256:a5866218f05961c7651a4a4a18d9bd0e5e5b4b26aafffb334df3423948db3560
ARG NGX_BROTLI_COMMIT=a71f9312c2deb28875acc7bacfdd5695a111aa53

# 1) Brotli modules compiled against the exact Nginx version (--with-compat).
FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f AS brotli
ARG NGINX_VERSION
ARG NGX_BROTLI_COMMIT
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git build-essential cmake libpcre2-dev zlib1g-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" | tar xz \
 && git clone --recurse-submodules https://github.com/google/ngx_brotli.git \
 && cd ngx_brotli && git checkout "${NGX_BROTLI_COMMIT}" && git submodule update --init --recursive \
 && cd deps/brotli && mkdir out && cd out \
 && cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF .. && cmake --build . --target brotlienc
RUN cd "nginx-${NGINX_VERSION}" \
 && ./configure --with-compat --add-dynamic-module=../ngx_brotli \
 && make modules

# 2) Production frontend build (no source maps served, spec §14.18).
FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build && find dist -name '*.map' -delete && rm -rf dist/.vite

# 3) Runtime: unprivileged Nginx (uid 101), read-only root friendly.
FROM nginxinc/nginx-unprivileged:${NGINX_VERSION}-trixie@${NGINX_RUNTIME_DIGEST} AS runtime
ARG NGINX_VERSION
# Apply Debian security updates at build time so fixed CVEs never wait for a base-image
# rebuild (the gate's Trivy step fails on fixable HIGH/CRITICAL, spec §16.5 step 7).
USER root
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=brotli /src/nginx-${NGINX_VERSION}/objs/ngx_http_brotli_filter_module.so /etc/nginx/modules/
COPY --from=brotli /src/nginx-${NGINX_VERSION}/objs/ngx_http_brotli_static_module.so /etc/nginx/modules/
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/security-headers.conf infra/nginx/proxy-api.conf /etc/nginx/
COPY infra/nginx/conf.d/ /etc/nginx/conf.d/
COPY --from=frontend /web/dist/ /usr/share/nginx/html/
USER 101
EXPOSE 8080 8443
# Uses the allowed Host: unknown hosts get 400 from the catch-all server (D16).
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -fsS -o /dev/null -H 'Host: localhost' http://127.0.0.1:8080/ || exit 1
