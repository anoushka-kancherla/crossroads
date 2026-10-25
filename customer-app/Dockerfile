FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG LOGO_URL=""
ENV VITE_LOGO_URL=$LOGO_URL
ARG STAFF_URL=""
ENV VITE_STAFF_URL=$STAFF_URL
RUN npm run build

# Serve the built files, and send /api to this app's own API only.
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
