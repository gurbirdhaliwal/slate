# "spa-build" image: builds the React SPA and serves it via Nginx, which also
# terminates for the API (§7). Build context is the REPO ROOT (needs infra/nginx).
FROM node:22-alpine AS build
WORKDIR /build
COPY apps/dashboard/package.json apps/dashboard/package-lock.json ./
RUN npm ci
COPY apps/dashboard .
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 80
