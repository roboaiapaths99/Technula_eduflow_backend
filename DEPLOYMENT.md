# 🚀 Technula EduFlow — Master Production Deployment & Google Play Release Guide

This guide provides the complete, production-grade instructions to deploy the entire **Technula EduFlow** platform:
- **Backend & Database**: Fast API + PostgreSQL behind SSL reverse proxy.
- **Frontend (Web)**: Unified Admin & Teacher portal served at **`https://eduflow.technula.com`**.
- **Mobile App**: Parent & Student Android App bundle (`.aab`) published to the **Google Play Store**.

---

## 🏗️ Architecture Overview

```
                          [DNS: eduflow.technula.com]
                                      │
                                      ▼
                        [VPS Nginx / SSL Port 443]
                       ┌──────────────┴──────────────┐
                       │                             │
                   path: /api/*                  path: /*
                       │                             │
                       ▼                             ▼
             [eduflow_backend:8000]        [eduflow_frontend:80]
              (FastAPI + Python 3.11)         (Vite + React SPA)
                       │
                       ▼
             [eduflow_db:5432]
             (PostgreSQL 15 Alpine)

  [Google Play Store] ───> [Android Mobile App] ───> https://eduflow.technula.com/api
```

---

## Part 1: DNS & Domain Setup (technula.com)

In your DNS provider (Cloudflare, GoDaddy, Hostinger, Namecheap, etc.):

1. Add an **A Record**:
   - **Type**: `A`
   - **Name / Host**: `eduflow` (or `technulaeduflow`)
   - **IPv4 Address**: `YOUR_VPS_PUBLIC_IP` (e.g. `123.45.67.89`)
   - **TTL**: `Auto` or `300` seconds
   - **Proxy Status**: DNS Only (or Proxied if using Cloudflare SSL)

2. Test DNS propagation:
   ```bash
   ping eduflow.technula.com
   ```
   Ensure it resolves to your VPS IP.

---

## Part 2: VPS Server Setup & Deployment

### 1. Connect to VPS & Install Docker
```bash
ssh root@YOUR_VPS_PUBLIC_IP

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install -y docker-compose-plugin docker-compose git certbot python3-certbot-nginx
```

### 2. Clone or Upload Codebase
```bash
cd /var/www
git clone <YOUR_GIT_REPO_URL> eduflow
cd /var/www/eduflow
```

### 3. Generate SSL Certificate with Let's Encrypt
```bash
# Temporarily stop any service using port 80
sudo systemctl stop nginx 2>/dev/null || true

# Obtain SSL Certificate
sudo certbot certonly --standalone -d eduflow.technula.com --agree-tos -m admin@technula.com --non-interactive
```
The certificates will be saved in `/etc/letsencrypt/live/eduflow.technula.com/`.

### 4. Create Production Environment File
```bash
cp .env.production.example .env
nano .env
```
Fill in:
- `POSTGRES_PASSWORD`: Strong unique database password.
- `JWT_SECRET_KEY`: Generate via `openssl rand -hex 32`.
- `GEMINI_API_KEY`: From Google AI Studio.
- `RESEND_API_KEY`: From Resend dashboard.
- `SUPERADMIN_PHONES`: Your phone number.

### 5. Launch Full Stack with Docker Compose
```bash
docker-compose up -d --build
```

### 6. Verify Services
```bash
# Check running containers
docker ps

# Check backend health
curl -I https://eduflow.technula.com/api/health

# Tail backend logs
docker logs -f eduflow_backend
```

Open your browser and navigate to: **`https://eduflow.technula.com`**.
Log in with your administrator or teacher credentials!

---

## Part 3: Parent & Student Mobile App (`parent_app`)

The mobile application is located in `parent_app/`. It is pre-configured with:
- **Package Name**: `com.technula.eduflow`
- **App Name**: `Technula EduFlow`
- **Production API URL**: `https://eduflow.technula.com/api`

### Step 1: Install Expo CLI & EAS CLI
On your local machine:
```bash
cd parent_app
npm install -g eas-cli
eas login
```
*(Create a free account at [expo.dev](https://expo.dev) if you don't have one).*

### Step 2: Configure EAS Project
```bash
eas project:init
```

### Step 3: Test Build a Standalone APK (Install on your phone directly)
```bash
eas build --platform android --profile preview
```
When finished, EAS will give you a QR code / download link for an `.apk` file you can install directly on any Android phone to test with your live server!

---

## Part 4: Publishing to Google Play Store

### 1. Google Play Developer Account
1. Go to [Google Play Console](https://play.google.com/console/signup).
2. Pay the one-time $25 registration fee and verify identity.

### 2. Create New App in Play Console
1. Click **Create app**.
2. App name: `Technula EduFlow`
3. Default language: `English (United States)` or `English (India)`
4. App or game: `App`
5. Free or paid: `Free`
6. Accept Declarations and click **Create app**.

### 3. Build Production Android App Bundle (`.aab`)
In `parent_app/`:
```bash
eas build --platform android --profile production
```
- EAS will ask: *Would you like to generate a new Android Keystore?* Select **Yes**.
- EAS builds your release bundle in the cloud and outputs a download link for `technula-eduflow-release.aab`.

### 4. Upload to Internal / Closed Testing
1. In Google Play Console, go to **Testing** > **Internal testing** (or **Closed testing**).
2. Click **Create new release**.
3. Upload the `.aab` file downloaded from the EAS build step.
4. Set Release name: `1.0.0 (1)`.
5. Enter Release notes: `Initial release of Technula EduFlow school management and parent communication app.`
6. Save and click **Review release** -> **Start rollout**.

### 5. Complete Store Listing & Content Rating
Fill out the mandatory sections in Play Console:
- **App Access**: Provide demo credentials (e.g. Test Parent login).
- **Target Audience**: Parents / Education (18+ or all ages with parental consent).
- **Privacy Policy**: Provide URL (e.g. `https://eduflow.technula.com/privacy` or hosted policy).
- **Data Safety Form**: Declare that the app collects Name, Email, and Phone number for school authentication and communication; all transmitted over HTTPS.
- **Store Graphics**:
  - App Icon: 512x512 PNG (from `assets/icon.png`)
  - Feature Graphic: 1024x500 PNG
  - Phone Screenshots: 2 to 8 high-resolution screenshots of the app.

### 6. Promote to Production
Once tested, click **Promote release** to **Production** and submit for Google review! Google typically approves in 24-72 hours.

---

## 🛠️ Routine Maintenance Commands

```bash
# Update code and re-deploy without downtime
cd /var/www/eduflow
git pull
docker-compose up -d --build

# View real-time logs
docker-compose logs -f backend

# Backup PostgreSQL Database
docker exec -t eduflow_db pg_dump -U technula_admin eduflow_db > backup_$(date +%Y%m%d).sql

# Renew SSL certificate (auto-renew cron)
sudo certbot renew --quiet && docker-compose restart nginx
```
