#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"ONX env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write ONX audit event into event_logs.")
    parser.add_argument("--env-file", required=True, help="Path to ONX env file")
    parser.add_argument("--entity-type", required=True, help="Audit entity type")
    parser.add_argument("--entity-id", default=None, help="Audit entity id")
    parser.add_argument("--message", required=True, help="Human-readable audit message")
    parser.add_argument("--level", default="info", choices=("info", "warning", "error"))
    parser.add_argument("--details-json", default="{}", help="JSON object with extra details")
    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    _load_env_file(env_file)

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from onx.db.models.event_log import EventLevel  # noqa: PLC0415
    from onx.db.session import SessionLocal  # noqa: PLC0415
    from onx.services.event_log_service import EventLogService  # noqa: PLC0415

    details = json.loads(args.details_json or "{}")
    if not isinstance(details, dict):
        raise ValueError("details-json must decode to an object.")

    db = SessionLocal()
    try:
        EventLogService().log(
            db,
            entity_type=args.entity_type,
            entity_id=args.entity_id,
            message=args.message,
            level=EventLevel(args.level),
            details=details,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
