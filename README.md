# Project Management System

Aplikasi project management berbasis **FastAPI + PostgreSQL**, dijalankan via Docker Compose.

## Fitur

- Dashboard KPI & statistik proyek
- Project Progress
- Task Management (Kanban Board)
- Project Timeline (Gantt Chart)
- Project Analytics
- Kalender deadline
- Team Management
- Login + captcha, MFA, trusted device

## Port lokal (dev)

| Service | Host Port | Container |
|---------|-----------|-----------|
| App     | **8891**  | `pm_app`  |
| Postgres| **5438**  | `pm_db`   |

## Menjalankan di lokal

```bash
docker compose up -d --build
```

Buka: http://localhost:8891

## CI/CD (otomatis ke VPS)

Setelah secrets GitHub dipasang, setiap `git push origin main` akan deploy ke VPS.

Panduan lengkap: [docs/CICD.md](docs/CICD.md)

## Deploy ke Cloud VPS

### 1. Persiapan server

- VPS Linux (Ubuntu 22.04/24.04 disarankan)
- Install Docker + Compose plugin
- Buka firewall untuk port app (contoh `8891`) atau `80/443` jika pakai reverse proxy

```bash
# contoh Ubuntu
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# logout/login agar group docker aktif
```

### 2. Upload kode ke VPS

```bash
# dari mesin lokal
scp -r ./project-management user@IP_VPS:~/
# atau git clone di VPS
```

### 3. Konfigurasi environment

```bash
cd ~/project-management
cp .env.example .env
nano .env
```

Isi minimal:

- `POSTGRES_PASSWORD` — password DB kuat
- `SECRET_KEY` — string acak panjang
- `APP_URL` — URL publik, contoh `http://IP_VPS:8891` atau `https://domain-anda`
- `COOKIE_SECURE=false` jika masih HTTP (IP:port); `true` jika sudah HTTPS
- `SEED_DATA=false`
- `DEFAULT_ADMIN_PASSWORD` — ganti dari default

### 4. Jalankan mode production

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Cek:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8891/api/health
```

Akses dari browser: `http://IP_VPS:8891`

### 5. (Opsional) Domain + HTTPS dengan Nginx

1. Arahkan DNS domain ke IP VPS
2. Proxy ke `127.0.0.1:8891`
3. Pasang sertifikat (Certbot)
4. Set di `.env`:
   - `APP_URL=https://domain-anda`
   - `COOKIE_SECURE=true`
5. Restart app: `docker compose -f docker-compose.prod.yml up -d`

Setelah HTTPS, login, MFA, dan konfirmasi device email memakai `APP_URL` yang benar.

### 6. SMTP

Di menu **Settings** aplikasi, isi SMTP agar email (welcome, MFA device confirm, reset password) terkirim.

## Perintah berguna di VPS

```bash
# log
docker compose -f docker-compose.prod.yml logs -f app

# rebuild setelah update kode
docker compose -f docker-compose.prod.yml up -d --build

# stop
docker compose -f docker-compose.prod.yml down
```

## Endpoint utama

- `GET /api/health`
- `GET /api/dashboard/kpi`
- `GET /api/dashboard/progress`
- `GET /api/dashboard/kanban`
- `GET /api/dashboard/timeline`
- `GET /api/dashboard/analytics`
- `GET /api/dashboard/calendar`
- `GET /api/dashboard/team`
- `GET/POST/PATCH/DELETE /api/projects`
- `GET/POST/PATCH/DELETE /api/tasks`
- `GET/POST/PATCH /api/team`
