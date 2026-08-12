FROM node:22-alpine AS builder

WORKDIR /build

COPY package*.json ./
RUN npm ci --only=production

COPY tsconfig.json ./
COPY src ./src

RUN npx tsc

# Production image
FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000

# Create non-root user
RUN addgroup -g 1001 -S nodejs
RUN adduser -S nodejs -u 1001

# Copy from builder
COPY --from=builder --chown=nodejs:nodejs /build/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /build/dist ./dist

# Copy static assets
COPY --chown=nodejs:nodejs src/web/dashboard.html ./dist/src/web/

# Create data directory
RUN mkdir -p /app/data && chown -R nodejs:nodejs /app/data

USER nodejs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/api/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

CMD ["node", "dist/src/web/server.js"]
