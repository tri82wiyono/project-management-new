"""Enrich existing List_Solusi tasks with Kanal Penerimaan Daerah (remap v3).

Does NOT create projects or tasks. Updates description on matching
Implementasi {project} — {pemda} tasks under Bidang Government.

Usage:
  python -m app.import_list_solusi_kanal_v3 --dry-run
  python -m app.import_list_solusi_kanal_v3
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Project, Task

DEFAULT_JSON = Path(__file__).resolve().parent / "data" / "list_solusi_kanal_v3_enrich.json"
OWNER_BIDANG_ID = 5
MARKER = "[kanal:itgov-list-solusi-2026-06]"

_KANAL_BLOCK_RE = re.compile(
    r"\n*Kanal Penerimaan Daerah:\n\[kanal:itgov-list-solusi-2026-06\][\s\S]*?(?=\n\n\[|\Z)",
    re.MULTILINE,
)


def _load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_pemda(value: str) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _apply_kanal_block(existing: str | None, block: str) -> str:
    base = (existing or "").strip()
    if MARKER in base:
        # Replace previous kanal block (from marker section header through end or next blank+header)
        cleaned = re.sub(
            r"(?:^|\n+)Kanal Penerimaan Daerah:\n" + re.escape(MARKER) + r"[\s\S]*$",
            "",
            base,
            count=1,
        ).rstrip()
        base = cleaned
    if not base:
        return block
    return f"{base}\n\n{block}"


def run_enrich(db: Session, payload: dict, *, dry_run: bool = False) -> dict:
    marker = payload.get("marker") or MARKER
    owner_bidang_id = int(payload.get("owner_bidang_id") or OWNER_BIDANG_ID)

    projects = {
        p.name: p
        for p in db.scalars(
            select(Project).where(Project.owner_bidang_id == owner_bidang_id)
        ).all()
    }

    updated = 0
    missing = 0
    skipped_same = 0
    details: list[dict] = []

    for item in payload.get("enrichments") or []:
        project_name = str(item["project_name"]).strip()
        pemda = str(item["pemda"]).strip()
        title = str(item.get("task_title") or f"Implementasi {project_name} — {pemda}").strip()
        block = str(item["kanal_block"]).strip()
        if marker not in block:
            block = f"{block}\n{marker}" if "Kanal Penerimaan Daerah:" in block else block

        project = projects.get(project_name)
        if not project:
            missing += 1
            details.append({"title": title, "action": "missing_project", "project": project_name})
            continue

        tasks = list(
            db.scalars(select(Task).where(Task.project_id == project.id)).all()
        )
        target = None
        want_pemda = _normalize_pemda(pemda)
        for task in tasks:
            ttitle = (task.title or "").strip()
            if ttitle == title:
                target = task
                break
            # fuzzy: same pemda suffix after em-dash / hyphen
            if "—" in ttitle:
                right = _normalize_pemda(ttitle.split("—", 1)[1])
                if right == want_pemda and project_name.lower() in ttitle.lower():
                    target = task
                    break
        if target is None:
            missing += 1
            details.append(
                {
                    "title": title,
                    "action": "missing_task",
                    "project": project_name,
                    "pemda": pemda,
                }
            )
            continue

        new_desc = _apply_kanal_block(target.description, block)
        if (target.description or "").strip() == new_desc.strip():
            skipped_same += 1
            details.append({"title": target.title, "action": "unchanged", "task_id": target.id})
            continue

        if dry_run:
            updated += 1
            details.append(
                {
                    "title": target.title,
                    "action": "dry_update",
                    "task_id": target.id,
                    "kanal_cells": item.get("kanal_cells"),
                    "jenis": item.get("jenis"),
                }
            )
            continue

        target.description = new_desc
        updated += 1
        details.append(
            {
                "title": target.title,
                "action": "updated",
                "task_id": target.id,
                "kanal_cells": item.get("kanal_cells"),
                "jenis": item.get("jenis"),
            }
        )

    if not dry_run:
        db.commit()

    return {
        "updated": updated,
        "missing": missing,
        "skipped_same": skipped_same,
        "dry_run": dry_run,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich List_Solusi tasks with kanal v3")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = _load_payload(args.json)
    db = SessionLocal()
    try:
        result = run_enrich(db, payload, dry_run=args.dry_run)
    finally:
        db.close()

    summary = {k: result[k] for k in ("updated", "missing", "skipped_same", "dry_run")}
    print(json.dumps(summary, indent=2))
    for row in result["details"]:
        extra = ""
        if row.get("kanal_cells") is not None:
            extra = f" cells={row['kanal_cells']}"
        print(f"- {row['action']}: {row.get('title')}{extra}")


if __name__ == "__main__":
    main()
