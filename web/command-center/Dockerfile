FROM node:20-alpine AS build
WORKDIR /app
COPY web/command-center/package*.json ./
RUN npm install
COPY web/command-center/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY web/command-center/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8030
