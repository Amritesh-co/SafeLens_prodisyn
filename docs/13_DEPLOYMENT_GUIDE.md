# Deployment Guide

Yes, you can host this application, but there is one **CRITICAL** constraint you must understand: **Your Database Connection**.

## 1. The "Private Database" Problem

Your database is at `192.168.1.42`. This is a **Private Local IP Address**.
*   **Works:** If you host the app on another computer in the *same office/network*.
*   **FAILS:** If you host the app on the **Cloud** (AWS, Heroku, Vercel, DigitalOcean).

**Why?**
Cloud servers cannot see inside your office network. They cannot reach `192.168.1.42`.

### Solution for Cloud Hosting
If you want to host this on the public internet, you must do one of the following:
1.  **Move the Database to the Cloud:** Migrate your PostgreSQL data to a cloud provider (e.g., AWS RDS, Supabase) so it has a Public IP.
2.  **VPN / Tunnel:** Set up a secure tunnel (like ngrok or a site-to-site VPN) so the cloud server can talk to your local office server. (Complex).
3.  **Use a Static Public IP:** If your office has a static IP, you can port-forward port 5432 (Dangerous without strict firewalls).

---

## 2. Production Checklist (If you solve the DB issue)

If you proceed with hosting, you must change these settings in `settings.py` for security:

### A. Security Settings
```python
# settings.py

# 1. Turn off Debug Mode (Critical for security)
DEBUG = False

# 2. Allow your domain name
ALLOWED_HOSTS = ['yourdomain.com', '192.168.1.38', 'localhost']
```

### B. Build the Frontend
You currently run `npm run dev`. In production, you must **build** it.

1.  **Build Command:**
    ```bash
    cd worker-safety-ui
    npm run build
    ```
2.  This creates a `dist/` folder with static HTML/JS files.
3.  You must serve these files using a web server like **Nginx** or **Apache**.

### C. CORS Settings
Update `CORS_ALLOWED_ORIGINS` in `settings.py` to match your new domain.
```python
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
]
```

## 3. Recommended "Local" Hosting
Since your data is local (`192.168.1.42`), the best "hosting" for you right now is exactly what you are doing (or moving it to a dedicated server in your office).

**To make it run permanently (without keeping a terminal open):**
Use a tool like **Gunicorn** and **Systemd** (Linux) to keep it running in the background.

**Command to run in background (Simple):**
```bash
nohup python3 manage.py runserver 0.0.0.0:8000 &
```
