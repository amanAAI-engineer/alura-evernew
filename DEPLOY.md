# Deploying ALURA EverNew to a server

You need: (1) a server, (2) a domain name pointing to it. Without a domain you can still test over `http://SERVER-IP`.

## Option A - VPS with Docker (recommended, ~15 minutes)
1. **Get a server**: any Ubuntu 22.04/24.04 VPS (DigitalOcean Bangalore, AWS Lightsail Mumbai, Hetzner, Hostinger...). 1 GB RAM is enough.
2. **Point your domain**: at your domain registrar add an **A record** `@` (and `www`) -> the server's IP address. Wait a few minutes.
3. **Install Docker** on the server (SSH in):
   ```
   curl -fsSL https://get.docker.com | sh
   ```
4. **Upload the project** (from your PC, in PowerShell, in the folder above `alura`):
   ```
   scp -r alura root@SERVER-IP:/opt/alura
   ```
   (or `git clone` it if you keep it on GitHub)
5. **Configure**: on the server
   ```
   cd /opt/alura
   cp .env.example .env
   nano .env
   ```
   Set at least: `DOMAIN=yourdomain.com`, `ADMIN_PASSWORD=<strong password>`, `SECRET_KEY=<long random text>`, company details, `ADMIN_EMAIL`, and `PAYMENT_MODE` (see below).
6. **Start**:
   ```
   docker compose up -d --build
   ```
   Caddy gets a free HTTPS certificate automatically. Visit `https://yourdomain.com`.
7. Open ports **80 and 443** in the provider's firewall.

Useful commands: `docker compose logs -f app` (logs) - `docker compose restart app` - `docker compose pull && docker compose up -d --build` (after updating code).

**Backups:** all data is in the `alura_data` volume (SQLite file). Back it up regularly:
```
docker compose cp app:/app/instance/alura.db ./backup-$(date +%F).db
```

## Option B - Managed platform (no server admin)
Render / Railway / Fly.io can deploy the included `Dockerfile` from a GitHub repo. Important: SQLite needs a **persistent disk** mounted at `/app/instance` (a paid feature on most platforms), otherwise orders are lost on every redeploy. Set the same environment variables from `.env.example` in the dashboard, plus `HTTPS=true`.

## Before taking real customers
- [ ] Real payment gateway connected (see README - demo payments must NOT be used live)
- [ ] Prices, company details, GSTIN filled in; legal pages reviewed
- [ ] Strong `ADMIN_PASSWORD` set in `.env`
- [ ] A test order placed on the live site; backups scheduled
