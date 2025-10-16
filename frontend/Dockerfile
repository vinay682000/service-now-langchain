# frontend/Dockerfile
# Stage 1: Build the React app
FROM node:lts-alpine AS builder
WORKDIR /app
# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci
# Copy source code and build
COPY . .
# The build command creates the 'build' folder
RUN npm run build

# Stage 2: Serve the app with Nginx
FROM nginx:alpine
# Copy the built app from the previous stage
COPY --from=builder /app/dist /usr/share/nginx/html
# Expose port 80
EXPOSE 80
# Nginx starts automatically by its base image's default command
# The environment variable REACT_APP_BACKEND_URL will be injected at runtime