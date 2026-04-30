# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /tmp/nginx.conf.template

# Only substitute BACKEND_FQDN — leave nginx's own $ variables untouched
CMD ["/bin/sh", "-c", "envsubst '${BACKEND_FQDN}' < /tmp/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]

EXPOSE 80
