# ⚡ Technula EduFlow — Core Backend API & Engine

High-performance, multi-tenant school operating system backend built with **FastAPI**, **SQLAlchemy**, **PostgreSQL**, **Google Gemini AI**, and **Celery/Background Tasks**.

---

## 🚀 Key Modules

- **Multi-Tenant Architecture**: Complete school tenant isolation via `TenantMiddleware` and JWT claims.
- **AI Diagnostics**: Google Gemini integration for student academic prognosis, at-risk early detection, and automated report card remarks.
- **Communication Suite**: Push notifications (Firebase FCM), SMS (DLT/MetaReach), Email (Resend), and WhatsApp Cloud API.
- **Academic Engine**: Attendance tracking, exam mark sheets, report card generation, timetable engine, daily student diary.
- **Operations & Billing**: Multi-tier fee collection with Razorpay, PayU SaaS subscriptions, gate pass visitor management, leave requests.
- **Cloud Storage**: Secure Cloudflare R2 / AWS S3 integration for documents, certificates, and media.

---

## 🛠️ Local Development

### 1. Create Virtual Environment
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Setup
```bash
cp .env.example .env
# Edit .env with your local settings (defaults to local SQLite database)
```

### 4. Run Server
```bash
python run.py
# Or with uvicorn:
uvicorn app:app --reload --port 8000
```
Interactive API documentation will be available at: `http://localhost:8000/docs`.

---

## 🐳 Production Deployment

Refer to **[DEPLOYMENT.md](DEPLOYMENT.md)** for instructions on deploying to Ubuntu VPS with Docker, Nginx, Let's Encrypt SSL, and PostgreSQL on `eduflow.technula.com`.
