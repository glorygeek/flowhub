#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


DEFAULT_MESSAGE = "你好，第一次使用 FlowHub，请先介绍一下项目、主要功能、相关插件和技能清单，并告诉我怎么安装。"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a FlowHub first-contact smoke test through OpenClaw. "
            "The script builds `openclaw --profile <name> agent ... --json` "
            "for onboarding verification."
        )
    )
    parser.add_argument("--profile-dir", required=True, help="OpenClaw profile directory")
    parser.add_argument("--agent-id", default="flowhub", help="Agent id used for the smoke test")
    parser.add_argument(
        "--openclaw-command",
        default="openclaw",
        help="Command used to invoke OpenClaw. Examples: `openclaw`, `cmd.exe /C openclaw`.",
    )
    parser.add_argument("--to", default="+15550004444", help="Destination used for the smoke test")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Smoke-test message")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved smoke-test command without running it.",
    )
    return parser


def build_smoke_command(args: argparse.Namespace, profile_name: str) -> list[str]:
    return [
        *command_tokens(args.openclaw_command),
        "--profile",
        profile_name,
        "agent",
        "--agent",
        args.agent_id,
        "--to",
        args.to,
        "--message",
        args.message,
        "--json",
    ]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir).expanduser()
    profile_name = infer_profile_name(profile_dir)
    full_command = build_smoke_command(args, profile_name)

    printable = " ".join(shlex.quote(part) for part in full_command)
    print("smoke test command:", printable)

    if args.print_only:
        return 0

    completed = subprocess.run(full_command)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
