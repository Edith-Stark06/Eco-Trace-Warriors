# EcoTrace Backend — multi-stage build (docs/engineering/11_DEPLOYMENT.md)

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
# Skip Husky Git hook installation inside the image (no .git, no hooks needed)
ENV HUSKY=0

COPY package.json package-lock.json* ./
COPY .husky/install.mjs ./.husky/install.mjs
COPY prisma ./prisma
RUN npm ci

COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Skip Husky Git hook installation inside the image (no .git, no hooks needed)
ENV HUSKY=0

COPY package.json package-lock.json* ./
COPY .husky/install.mjs ./.husky/install.mjs
COPY prisma ./prisma
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/dist ./dist

# Run as the non-root user provided by the node image
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/v1/health || exit 1

CMD ["node", "dist/server.js"]
