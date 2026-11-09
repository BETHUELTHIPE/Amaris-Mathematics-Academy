FROM node:24-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
COPY vendor ./vendor

RUN npm ci

COPY . .

RUN npm run build

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

EXPOSE 3000

CMD ["npx", "vinext", "start", "--host", "0.0.0.0", "--port", "3000"]
