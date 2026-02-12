FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .
ARG VITE_BUILD_ID=dev-local
ARG VITE_BUILD_TIME_UTC=unknown
ENV VITE_BUILD_ID=${VITE_BUILD_ID}
ENV VITE_BUILD_TIME_UTC=${VITE_BUILD_TIME_UTC}
RUN npm run build

FROM nginx:1.27-alpine
WORKDIR /usr/share/nginx/html

COPY --from=builder /app/dist ./
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV PORT=8080
EXPOSE 8080

CMD ["/bin/sh", "-c", "envsubst '$PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
