# ──────────────────────────────────────────────────────────────────────────────
# LumeOps Frontend — Multi-stage production build
# Stage 1: Build React app with Vite
# Stage 2: Serve static assets with nginx (unprivileged)
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first (better Docker layer caching)
COPY package.json package-lock.json ./

# Install dependencies (ci = exact versions from lockfile)
RUN npm ci --ignore-scripts

# Copy source code
COPY . .

# Build for production
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Remove default nginx content
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx configuration with security headers and SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Create non-root user for nginx
RUN addgroup -g 1001 -S lumeops && \
    adduser -S -D -H -u 1001 -h /usr/share/nginx/html -s /sbin/nologin -G lumeops lumeops && \
    chown -R lumeops:lumeops /usr/share/nginx/html && \
    chown -R lumeops:lumeops /var/cache/nginx && \
    chown -R lumeops:lumeops /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown -R lumeops:lumeops /var/run/nginx.pid

EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

USER lumeops

CMD ["nginx", "-g", "daemon off;"]
