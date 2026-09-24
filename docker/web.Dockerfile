# Frontend image: static build served by nginx, which also proxies /api to the backend.
#   docker build -f docker/web.Dockerfile -t leadtracker-web .
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
COPY packages/shared packages/shared
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN pnpm --filter @leadtracker/web build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
ENV API_UPSTREAM=http://api:8000
EXPOSE 80
