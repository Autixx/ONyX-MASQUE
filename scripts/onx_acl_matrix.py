#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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


def _write_json(path: Path | None, payload: dict) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or import ONX ACL matrix via DB.")
    parser.add_argument("--env-file", default="/etc/onx/onx.env", help="Path to ONX env file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export effective ACL matrix")
    export_parser.add_argument("--output", default="-", help="Output file path or - for stdout")

    export_defaults_parser = subparsers.add_parser("export-defaults", help="Export built-in default ACL matrix")
    export_defaults_parser.add_argument("--output", default="-", help="Output file path or - for stdout")

    import_parser = subparsers.add_parser("import", help="Import ACL overrides into DB")
    import_parser.add_argument("--input", required=True, help="Input JSON file")
    import_parser.add_argument("--replace", action="store_true", help="Delete DB overrides not present in input")

    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    _load_env_file(env_file)

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from onx.api.security.admin_access import admin_access_control  # noqa: PLC0415
    from onx.db.models.event_log import EventLevel  # noqa: PLC0415
    from onx.db.session import SessionLocal  # noqa: PLC0415
    from onx.schemas.access_rules import AccessRuleUpsert  # noqa: PLC0415
    from onx.services.access_rule_service import AccessRuleService  # noqa: PLC0415
    from onx.services.event_log_service import EventLogService  # noqa: PLC0415

    db = SessionLocal()
    access_rule_service = AccessRuleService()
    event_log_service = EventLogService()
    try:
        if args.command == "export":
            payload = {
                "version": 1,
                "kind": "effective_acl_matrix",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": admin_access_control.describe_permission_matrix(db),
            }
            output = None if args.output == "-" else Path(args.output).resolve()
            _write_json(output, payload)
            return 0

        if args.command == "export-defaults":
            items = []
            for permission_key, meta in sorted(admin_access_control.DEFAULT_PERMISSION_MATRIX.items()):
                items.append(
                    {
                        "permission_key": permission_key,
                        "description": meta.get("description"),
                        "source": "default",
                        "allowed_roles": list(meta["roles"]),
                        "enabled": True,
                    }
                )
            payload = {
                "version": 1,
                "kind": "default_acl_matrix",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": items,
            }
            output = None if args.output == "-" else Path(args.output).resolve()
            _write_json(output, payload)
            return 0

        if args.command == "import":
            input_path = Path(args.input).resolve()
            document = json.loads(input_path.read_text(encoding="utf-8"))
            items = document.get("items") if isinstance(document, dict) else document
            if not isinstance(items, list):
                raise ValueError("Input JSON must be a list or an object with 'items'.")

            seen_permission_keys: set[str] = set()
            upserted_count = 0
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Each ACL item must be an object.")
                permission_key = str(item.get("permission_key") or "").strip()
                if not permission_key:
                    raise ValueError("Each ACL item must include permission_key.")
                payload = AccessRuleUpsert(
                    description=item.get("description"),
                    allowed_roles=list(item.get("allowed_roles") or []),
                    enabled=bool(item.get("enabled", True)),
                )
                access_rule_service.upsert_rule(db, permission_key, payload)
                seen_permission_keys.add(permission_key)
                upserted_count += 1

            deleted_permission_keys: list[str] = []
            if args.replace:
                existing_rules = access_rule_service.list_rules(db)
                for rule in existing_rules:
                    if rule.permission_key in seen_permission_keys:
                        continue
                    deleted_permission_keys.append(rule.permission_key)
                    access_rule_service.delete_rule(db, rule)

            event_log_service.log(
                db,
                entity_type="acl_matrix",
                entity_id=None,
                level=EventLevel.INFO,
                message="ACL matrix imported.",
                details={
                    "source_file": str(input_path),
                    "replace": bool(args.replace),
                    "upserted_count": upserted_count,
                    "deleted_permission_keys": deleted_permission_keys,
                },
            )
            result = {
                "status": "ok",
                "upserted_count": upserted_count,
                "deleted_permission_keys": deleted_permission_keys,
            }
            sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
            return 0

        raise ValueError(f"Unsupported command: {args.command}")
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
