# CI/CD — Deploy otomatis ke VPS

Alur: **push ke `main` di GitHub → GitHub Actions SSH ke VPS → `git pull` + rebuild Docker**.

Laptop hanya dipakai untuk develop + `git push`. Deploy tidak perlu dijalankan manual dari laptop.

---

## 1) Di VPS (sekali saja)

Pastikan repo sudah ada (sudah ada di `/opt/project-management-new`).

### A. Deploy key agar VPS bisa `git pull` (repo private)

Di VPS:

```bash
ssh-keygen -t ed25519 -f /root/.ssh/pm_github_deploy -N "" -C "pm-vps-deploy"
cat /root/.ssh/pm_github_deploy.pub
```

Di GitHub repo → **Settings → Deploy keys → Add deploy key**:
- Title: `vps-project-management`
- Key: isi isi `.pub` di atas
- Centang **Allow read access** (cukup read)

Di VPS, pakai key itu untuk GitHub:

```bash
cat >> /root/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile /root/.ssh/pm_github_deploy
  IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config

cd /opt/project-management-new
git remote set-url origin git@github.com:tri82wiyono/project-management-new.git
git fetch origin
```

### B. SSH key khusus untuk GitHub Actions (masuk ke VPS)

Di **laptop** (disarankan key terpisah, jangan pakai key pribadi harian):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pm_gha_deploy -N "" -C "github-actions-pm"
```

Salin **public key** ke VPS:

```bash
# dari laptop
ssh-copy-id -i ~/.ssh/pm_gha_deploy.pub root@187.77.141.193
# atau manual:
# cat ~/.ssh/pm_gha_deploy.pub  →  append ke /root/.ssh/authorized_keys di VPS
```

Uji:

```bash
ssh -i ~/.ssh/pm_gha_deploy root@187.77.141.193 'echo ok && hostname'
```

---

## 2) Di GitHub (sekali saja)

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Contoh / isi |
|--------|----------------|
| `VPS_HOST` | `187.77.141.193` |
| `VPS_USER` | `root` |
| `VPS_PORT` | `22` (opsional) |
| `VPS_APP_DIR` | `/opt/project-management-new` (opsional) |
| `VPS_SSH_KEY` | **private key** penuh dari `~/.ssh/pm_gha_deploy` (termasuk baris `BEGIN`/`END`) |

Jangan commit private key ke git.

---

## 3) Di laptop (setiap update)

```bash
git add .
git commit -m "pesan commit"
git push origin main
```

Lalu cek: GitHub → tab **Actions** → workflow **Deploy to VPS**.

Atau deploy manual: Actions → Deploy to VPS → **Run workflow**.

---

## Catatan penting

- File `.env` di VPS **tidak** ditimpa CI/CD (`git reset --hard` tidak menyentuh file untracked, tapi jika `.env` pernah di-commit, hati-hati). Saat ini `.env` di-ignore — biarkan `.env` hanya di VPS.
- Setelah deploy, app rebuild image; DB & volume upload tetap aman.
- Jika Actions gagal SSH: cek firewall VPS port 22 untuk IP GitHub Actions (dinamis) — atau pakai self-hosted runner di VPS (lebih ketat).

### Opsi lebih aman (opsional): self-hosted runner di VPS

Kalau port 22 tidak ingin dibuka ke internet luas:

1. VPS: install [GitHub Actions runner](https://docs.github.com/en/actions/hosting-your-own-runners)
2. Workflow ganti `runs-on: self-hosted`
3. Tidak perlu buka SSH dari GitHub cloud ke VPS

---

## Troubleshooting cepat

| Gejala | Cek |
|--------|-----|
| Permission denied (SSH) | Secret `VPS_SSH_KEY` salah / belum di `authorized_keys` |
| Permission denied (git fetch) | Deploy key GitHub belum dipasang di VPS |
| Health check failed | `docker compose -f docker-compose.prod.yml logs app` di VPS |
| `.env` hilang/salah | Jangan commit `.env`; restore dari backup VPS |
