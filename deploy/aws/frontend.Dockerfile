FROM node:24-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
COPY vendor/ ./vendor/
RUN npm ci --include=dev --no-audit --no-fund \
    && npm install --no-save --package-lock=false --no-audit --no-fund \
       nitro@3.0.260903-beta @tailwindcss/vite@4.3.3
COPY . .
RUN NODE_ENV=production NITRO_PRESET=node npm exec -- vite build --config vite.node.config.ts

FROM node:24-bookworm-slim AS runtime

ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
