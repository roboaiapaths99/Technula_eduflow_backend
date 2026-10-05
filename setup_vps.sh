#!/bin/bash
# ==============================================================================
# Technula EduFlow — Automated VPS Deployment Setup Script
# Domain: technulaeduflow.technula.com
# ==============================================================================
set -e

DOMAIN="technulaeduflow.technula.com"
EMAIL="admin@technula.com"

echo "=========================================================="
echo "🚀 Starting Technula EduFlow Automated Deployment Setup"
echo "Target Domain: https://${DOMAIN}"
echo "=========================================================="

# 1. Update system & install dependencies
echo "📦 Updating OS and installing Docker & Certbot..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git certbot

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo apt install -y docker-compose-plugin docker-compose
fi

# 2. Setup project directories
PROJECT_ROOT="/var/www/eduflow"
sudo mkdir -p ${PROJECT_ROOT}
sudo chown -R $USER:$USER ${PROJECT_ROOT}
cd ${PROJECT_ROOT}

# 3. Clone or update Backend & Frontend repositories
if [ ! -d "backend" ]; then
    echo "📥 Cloning Backend repository..."
    git clone https://github.com/roboaiapaths99/Technula_eduflow_backend.git backend
else
    echo "🔄 Pulling latest Backend..."
    cd backend && git pull && cd ..
fi

if [ ! -d "frontend" ]; then
    echo "📥 Cloning Admin & Teacher Frontend repository..."
    git clone https://github.com/roboaiapaths99/Technula_eduflow_admin.git frontend
else
    echo "🔄 Pulling latest Frontend..."
    cd frontend && git pull && cd ..
fi

# 4. Copy orchestration files to project root
cp backend/docker-compose.yml ./docker-compose.yml
cp -r backend/nginx ./nginx

if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env configuration from template..."
    cp backend/.env.production.example .env
    echo "⚠️ NOTE: Please review and edit .env with your real credentials if needed."
fi

# 5. Obtain Let's Encrypt SSL Certificate
echo "🔒 Requesting Let's Encrypt SSL certificate for ${DOMAIN}..."
sudo systemctl stop nginx 2>/dev/null || true
sudo certbot certonly --standalone -d ${DOMAIN} --agree-tos -m ${EMAIL} --non-interactive || {
    echo "⚠️ Certbot could not verify domain. Ensure DNS A record for ${DOMAIN} points to this VPS IP."
}

# 6. Build and launch all Docker containers
echo "🐳 Launching Docker Compose stack (Database, Backend, Frontend, Nginx)..."
docker-compose down 2>/dev/null || true
docker-compose up -d --build

echo "=========================================================="
echo "🎉 SUCCESS: Technula EduFlow is now running!"
echo "🌐 Web Portal (Admin & Teacher): https://${DOMAIN}"
echo "⚡ Backend API Endpoint:        https://${DOMAIN}/api"
echo "📱 Mobile App API URL:          https://${DOMAIN}/api"
echo "=========================================================="
