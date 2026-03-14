from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_session_factory, migrate_db
from app.services.clawhub_sync import sync_clawhub_skills


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync ClawHub skills into the local FlowHub index.")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Fetch detail payloads for every remote skill instead of only changed entries.",
    )
    args = parser.parse_args()

    migrate_db()
    with get_session_factory()() as db:
        result = sync_clawhub_skills(db, full_refresh=args.full_refresh)
    print(asdict(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
