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

## Port (hindari bentrok)

| Service | Host Port | Container |
|---------|-----------|-----------|
| App     | **8891**  | `pm_app`  |
| Postgres| **5438**  | `pm_db`   |

Image DB: `postgres:16-alpine` (sudah ada di mesin lokal).

## Menjalankan

```bash
docker compose up -d --build
```

Buka: [http://localhost:8891](http://localhost:8891)

API docs: [http://localhost:8891/docs](http://localhost:8891/docs)

Health: [http://localhost:8891/api/health](http://localhost:8891/api/health)

## Stop

```bash
docker compose down
```

## Endpoint utama

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
# project-management-new
