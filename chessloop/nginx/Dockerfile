# Reverse proxy with its config built in (no bind mount: F-042).
# nginx stable branch; see https://nginx.org/en/download.html
FROM nginx:1.30-alpine
COPY default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
