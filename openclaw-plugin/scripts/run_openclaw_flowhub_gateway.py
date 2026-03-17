#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path


def infer_profile_name(profile_dir: Path) -> str:
    name = profile_dir.name
    if name.startswith(".openclaw-"):
        return name[len(".openclaw-") :]
    if name == ".openclaw":
        return "default"
    return name


def command_tokens(command: str) -> list[str]:
    tokens = shlex.split(command)
    if not tokens:
        raise ValueError("openclaw command is empty")
    return tokens


def load_config(profile_dir: Path) -> dict:
    config_path = profile_dir / "openclaw.json"
    if not config_path.exists():
        raise FileNotFoundError(f"openclaw.json not found in profile directory: {profile_dir}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an OpenClaw gateway for a FlowHub profile in the foreground. "
            "The script reads gateway settings from openclaw.json and builds the "
            "matching `openclaw --profile <name> gateway run ...` command."
        )
    )
    parser.add_argument("--profile-dir", required=True, help="OpenClaw profile directory")
    parser.add_argument(
        "--openclaw-command",
        default="openclaw",
        help="Command used to invoke OpenClaw. Examples: `openclaw`, `cmd.exe /C openclaw`.",
    )
    parser.add_argument("--force", action="store_true", help="Pass --force to `gateway run`.")
    parser.add_argument("--verbose", action="store_true", help="Pass --verbose to `gateway run`.")
    parser.add_argument(
        "--claude-cli-logs",
        action="store_true",
        help="Pass --claude-cli-logs to `gateway run`.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Pass --compact to `gateway run`.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved gateway command without running it.",
    )
    return parser


def build_gateway_command(args: argparse.Namespace, profile_name: str, config: dict) -> list[str]:
    gateway = config.get("gateway", {})
    bind = gateway.get("bind", "loopback")
    port = gateway.get("port", 18789)
    auth = gateway.get("auth", {})
    auth_mode = auth.get("mode")
    token = auth.get("token")

    full_command = [
        *command_tokens(args.openclaw_command),
        "--profile",
        profile_name,
        "gateway",
        "run",
        "--port",
        str(port),
        "--bind",
        str(bind),
    ]

    if auth_mode:
        full_command.extend(["--auth", str(auth_mode)])
    if auth_mode == "token" and token:
        full_command.extend(["--token", str(token)])
    if args.force:
        full_command.append("--force")
    if args.verbose:
        full_command.append("--verbose")
    if args.claude_cli_logs:
        full_command.append("--claude-cli-logs")
    if args.compact:
        full_command.append("--compact")
    return full_command


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir).expanduser()
    profile_name = infer_profile_name(profile_dir)
    config = load_config(profile_dir)
    full_command = build_gateway_command(args, profile_name, config)

    printable = " ".join(shlex.quote(part) for part in full_command)
    print("gateway run command:", printable)

    if args.print_only:
        return 0

    completed = subprocess.run(full_command)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
