# C360 frontend: build the Vite SPA, then serve it with nginx (free UBI images
# from the Red Hat public registry, non-root).
FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:latest AS build
WORKDIR /opt/app-root/src

# Build-time only (Vite inlines it). A relative URL keeps the SPA and API on the
# same origin behind nginx, so no CORS configuration is needed.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY --chown=1001:0 package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY --chown=1001:0 . .
RUN npm run build

FROM registry.access.redhat.com/ubi9/nginx-126:latest
# The base image's default server listens on 8080 as a non-root user and
# includes nginx.default.d/*.conf at server level.
COPY --from=build --chown=1001:0 /opt/app-root/src/dist/ /opt/app-root/src/
COPY --chown=1001:0 nginx.conf /opt/app-root/etc/nginx.default.d/c360.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
