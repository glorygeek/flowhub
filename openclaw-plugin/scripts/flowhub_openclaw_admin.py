#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent
SUBCOMMAND_SCRIPTS = {
    "bootstrap": SCRIPT_ROOT / "bootstrap_openclaw_flowhub.py",
    "gateway": SCRIPT_ROOT / "run_openclaw_flowhub_gateway.py",
    "smoke": SCRIPT_ROOT / "run_openclaw_flowhub_smoke.py",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unified FlowHub OpenClaw admin entrypoint. "
            "Use subcommands to bootstrap a profile, run a foreground gateway, "
            "or execute a first-contact smoke test."
        )
    )
    parser.add_argument("command", nargs="?", choices=("bootstrap", "gateway", "smoke"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    script_path = SUBCOMMAND_SCRIPTS[args.command]
    forwarded = list(args.args)
    full_command = [sys.executable, str(script_path), *forwarded]

    print("admin dispatch:", " ".join(shlex.quote(part) for part in full_command))
    completed = subprocess.run(full_command)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
