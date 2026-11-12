# Build against the reviewed FRONTEND checkout, not this backend branch's old frontend.
FROM node:24-bookworm-slim AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
COPY frontend/vendor ./vendor
RUN npm ci --include=dev
# Explicit source directories keep root .env files and local artifacts out of layers.
COPY frontend/app ./app
COPY frontend/components ./components
COPY frontend/lib ./lib
COPY frontend/public ./public
COPY frontend/hooks ./hooks
COPY frontend/data ./data
COPY frontend/db ./db
COPY frontend/drizzle ./drizzle
COPY frontend/node ./node
COPY frontend/worker ./worker
COPY frontend/build ./build
COPY frontend/types ./types
COPY frontend/scripts ./scripts
COPY frontend/examples ./examples
COPY frontend/email-templates ./email-templates
COPY frontend/supabase ./supabase
COPY frontend/.openai/hosting.json ./.openai/hosting.json
COPY frontend/*.ts frontend/*.mjs frontend/components.json frontend/tsconfig.json ./
RUN npm install --no-save --package-lock=false nitro@3.0.260903-beta @tailwindcss/vite@4.3.3
ENV NODE_ENV=production
RUN NITRO_PRESET=node npx vite build --config vite.node.config.ts

FROM node:24-bookworm-slim
WORKDIR /app
ARG FRONTEND_REVISION=unknown
LABEL org.opencontainers.image.revision=$FRONTEND_REVISION
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/frontend/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
