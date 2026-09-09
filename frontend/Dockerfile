# Etapa 1: dependencias + build de producción
# Nota: al ser una SPA (ssr: false), la configuración pública se incrusta en el
# cliente durante el build; para cambiar la API hay que pasarla como build-arg:
#   docker build --build-arg NUXT_PUBLIC_API_BASE=http://synapse-backend:8000 .
FROM oven/bun:1 AS build
WORKDIR /app

ARG NUXT_PUBLIC_API_BASE=http://localhost:8000
ARG NUXT_PUBLIC_WS_BASE=ws://localhost:8000
ENV NUXT_PUBLIC_API_BASE=$NUXT_PUBLIC_API_BASE
ENV NUXT_PUBLIC_WS_BASE=$NUXT_PUBLIC_WS_BASE

COPY package.json bun.lock* ./
RUN bun install

COPY . .
RUN bun run build

# Etapa 2: servidor de producción (Nitro, puerto 3000)
FROM oven/bun:1
WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=3000
ENV NITRO_HOST=0.0.0.0
ENV NITRO_PORT=3000

COPY --from=build /app/.output /app/.output

EXPOSE 3000

CMD ["bun", ".output/server/index.mjs"]
