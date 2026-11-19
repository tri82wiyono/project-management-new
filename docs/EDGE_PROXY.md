# Edge proxy isolation (PM vs MIS2)

Kedua app di VPS yang sama, di belakang `psr-waf`.

| Host | Backend |
|---|---|
| `mis2.banksumut.co.id` | `psr-viewer:8000` |
| `pm.banksumut.co.id` | `pm_app:8000` |

## Kenapa PM bisa “nyasar” ke MIS2 setelah deploy MIS2?

Deploy MIS2 menjalankan `git reset --hard` lalu recreate `psr-waf`.
Config default WAF hanya `server_name mis2.banksumut.co.id`, jadi request ke `pm.*`
jatuh ke default server (= MIS2) bila overlay PM tidak ikut di-mount.

## Proteksi di VPS (sudah dipasang)

Lokasi di luar repo MIS2 (aman dari `git reset --hard`):

- `/opt/pm-edge/pm.conf.template`
- `/opt/pm-edge/docker-compose.edge.pm.yml`
- `/usr/local/sbin/ensure-pm-waf-proxy.sh`
- systemd timer `ensure-pm-waf-proxy.timer` (cek tiap ~60 detik, auto-repair)

Manual repair:

```bash
sudo /usr/local/sbin/ensure-pm-waf-proxy.sh
```

## PM `.env` produksi

```env
APP_URL=https://pm.banksumut.co.id
COOKIE_SECURE=true
```
