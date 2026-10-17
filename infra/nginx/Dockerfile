# syntax=docker/dockerfile:1.7
# Edge image: unprivileged Nginx + brotli dynamic modules + the production SPA build.
# Build context: repository root.
ARG NGINX_VERSION=1.28.0
ARG NGX_BROTLI_COMMIT=a71f9312c2deb28875acc7bacfdd5695a111aa53

# 1) Brotli modules compiled against the exact Nginx version (--with-compat).
FROM debian:bookworm-slim AS brotli
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
FROM node:20-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build && find dist -name '*.map' -delete

# 3) Runtime: unprivileged Nginx (uid 101), read-only root friendly.
FROM nginxinc/nginx-unprivileged:${NGINX_VERSION}-bookworm AS runtime
ARG NGINX_VERSION
COPY --from=brotli /src/nginx-${NGINX_VERSION}/objs/ngx_http_brotli_filter_module.so /etc/nginx/modules/
COPY --from=brotli /src/nginx-${NGINX_VERSION}/objs/ngx_http_brotli_static_module.so /etc/nginx/modules/
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/security-headers.conf infra/nginx/proxy-api.conf /etc/nginx/
COPY infra/nginx/conf.d/ /etc/nginx/conf.d/
COPY --from=frontend /web/dist/ /usr/share/nginx/html/
USER 101
EXPOSE 8080 8443
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD curl -fsS -o /dev/null http://127.0.0.1:8080/ || exit 1
