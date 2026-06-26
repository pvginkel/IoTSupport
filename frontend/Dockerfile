# Multi-stage build for the React frontend with NGINX deployment.
# Built from the monorepo root context (the frontend is a pnpm workspace member,
# so the install needs the root pnpm-workspace.yaml + pnpm-lock.yaml).
FROM node:lts-slim AS build

# Install pnpm (pin to the workspace's packageManager version)
RUN corepack enable && corepack prepare pnpm@10.28.1 --activate

# Set working directory
WORKDIR /app

# Copy workspace config and member manifests for dependency caching
# (workspace-aware install from the root).
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/
COPY tools/code_health/cognitive/package.json tools/code_health/cognitive/

# Install dependencies (workspace-aware)
RUN pnpm install --frozen-lockfile

# Copy source code, configuration files, and cached OpenAPI schema
COPY . .

# Build the frontend (uses the cached OpenAPI schema)
RUN cd frontend && pnpm build

# Production stage with NGINX
FROM nginx:alpine AS production

# Copy custom NGINX configuration and proxy snippet
COPY frontend/nginx.conf /etc/nginx/nginx.conf
RUN mkdir -p /etc/nginx/snippets
COPY frontend/snippets/proxy.conf /etc/nginx/snippets/proxy.conf

# Copy built static assets from build stage
COPY --from=build /app/frontend/dist /usr/share/nginx/html

# Expose port 3100
EXPOSE 3100

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
