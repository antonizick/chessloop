# Node 24 is the active LTS line (supported until 2028-04-30):
# https://github.com/nodejs/Release/blob/main/schedule.json
FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# nginx stable branch; see https://nginx.org/en/download.html
FROM nginx:1.30-alpine
# Alpine's security fixes reach its packages before the next nginx image.
RUN apk upgrade --no-cache
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
