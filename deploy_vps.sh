#!/bin/bash
# ==============================================================================
# Technula EduFlow — Production Deploy Script (Uses Host Nginx & Port 8087)
# ==============================================================================
set -e

DOMAIN="technulaeduflow.technula.com"
EMAIL="admin@technula.com"

echo "=========================================================="
echo "🚀 Deploying Technula EduFlow on ${DOMAIN}"
echo "Backend: Port 8087 | Frontend: Port 3000 | SSL: Host Nginx"
echo "=========================================================="

cd /var/www/eduflow

# 1. Generate clean docker-compose.yml
cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: eduflow_db
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-technula_admin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-StrongDbPassword2026!EduFlow}
      POSTGRES_DB: ${POSTGRES_DB:-eduflow_db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-technula_admin} -d ${POSTGRES_DB:-eduflow_db}"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: eduflow_backend
    restart: always
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "8087:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-technula_admin}:${POSTGRES_PASSWORD:-StrongDbPassword2026!EduFlow}@db:5432/${POSTGRES_DB:-eduflow_db}
    volumes:
      - backend_uploads:/app/static/uploads
      - backend_assets:/app/static/school_assets

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        VITE_API_BASE: ""
    container_name: eduflow_frontend
    restart: always
    ports:
      - "8088:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  backend_uploads:
  backend_assets:
EOF

# 2. Build and launch Docker containers
echo "🐳 Building and starting Docker containers..."
docker-compose up -d --build

# 3. Configure existing Host Nginx
echo "⚙️ Configuring Host Nginx for ${DOMAIN}..."
sudo tee /etc/nginx/sites-available/${DOMAIN} > /dev/null << 'EOF'
server {
    listen 80;
    server_name eduflow.technula.com;
    client_max_body_size 100M;

    location /api/ {
        proxy_pass http://127.0.0.1:8087/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8087/static/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 4. Request SSL certificate without stopping existing Nginx
echo "🔒 Securing with Let's Encrypt SSL..."
sudo certbot --nginx -d ${DOMAIN} --agree-tos -m ${EMAIL} --non-interactive --redirect

echo "=========================================================="
echo "🎉 SUCCESS: Technula EduFlow is now fully deployed!"
echo "🌐 Web Portal (Admin & Teacher): https://${DOMAIN}"
echo "⚡ Backend API (Direct):        http://YOUR_VPS_IP:8087"
echo "⚡ Backend API (SSL):           https://${DOMAIN}/api"
echo "=========================================================="
