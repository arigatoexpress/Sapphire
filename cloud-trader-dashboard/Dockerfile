# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Set environment to force rollup to use JS instead of native binaries
ENV ROLLUP_SKIP_NODEJS_NATIVE_DEPS=true

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Install envsubst for config templating
RUN apk add --no-cache gettext

# Copy built application
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 8080

# Set default PORT if not provided
ENV PORT=8080

# Use envsubst to substitute environment variables in nginx config
CMD ["/bin/sh", "-c", "envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
