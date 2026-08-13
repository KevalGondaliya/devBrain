# DevBrain frontend (Phase 9) — Next.js App Router, multi-stage Node build.
#
# Unlike every other Dockerfile in this repo (uv workspace member, context =
# repo root), this one is self-contained: `frontend/` has no workspace
# dependency on `packages/common` or any Python service, so its build
# context is just `frontend/` itself. See docker-compose.yml's `frontend`
# stanza for the actual `build.context`/`dockerfile` wiring.
#
# `NEXT_PUBLIC_API_URL` is a *build-time* arg (Next.js inlines
# `NEXT_PUBLIC_*` env vars into the client JS bundle at build time, not at
# container start) — passed via `docker-compose.yml`'s `build.args`, not
# `environment:`. See that stanza's comment for why the value must be a
# browser-reachable URL, not the compose-internal service DNS name.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:20-slim AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Direct binary invocation, not `npm run build` — this repo's dev host has
# a colon in its path (see PROGRESS_REPORT.md Phase 9), which breaks npm's
# PATH-based bin resolution for `npm run`/`npx`. The container's own build
# path (`/app`) has no colon, so this isn't strictly required *inside*
# Docker, but kept consistent with how this project actually runs the build
# everywhere else so the same command is verified in both places.
RUN ./node_modules/.bin/next build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.mjs ./next.config.mjs
EXPOSE 3000
CMD ["./node_modules/.bin/next", "start", "-p", "3000"]
