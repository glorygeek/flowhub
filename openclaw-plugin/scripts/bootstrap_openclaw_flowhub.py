#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import shlex
import subprocess
import sys
from os import PathLike
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SAMPLE = PLUGIN_ROOT / "examples" / "openclaw.local.sample.jsonc"
VPS_SAMPLE = PLUGIN_ROOT / "examples" / "openclaw.vps.sample.jsonc"
WORKSPACE_AGENTS_SAMPLE = PLUGIN_ROOT / "examples" / "flowhub.workspace.AGENTS.sample.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_profile_name(profile_dir: Path) -> str:
    name = profile_dir.name
    if name.startswith(".openclaw-"):
        return name[len(".openclaw-") :]
    if name == ".openclaw":
        return "default"
    return name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap a dedicated OpenClaw profile + workspace for FlowHub. "
            "This writes openclaw.json, copies the FlowHub workspace AGENTS.md template, "
            "and generates a next-steps guide."
        )
    )
    parser.add_argument("--mode", choices=["local", "vps"], default="local")
    parser.add_argument("--profile-dir", required=True, help="Target OpenClaw profile directory")
    parser.add_argument("--workspace-dir", required=True, help="Target FlowHub workspace directory")
    parser.add_argument("--api-base-url", help="FlowHub API base URL")
    parser.add_argument("--api-key", required=True, help="FlowHub API key")
    parser.add_argument("--gateway-port", type=int, default=18789, help="Gateway port")
    parser.add_argument("--gateway-token", help="Gateway token; generated automatically if omitted")
    parser.add_argument("--agent-id", default="flowhub", help="OpenClaw agent id")
    parser.add_argument("--agent-name", default="FlowHub", help="OpenClaw agent display name")
    parser.add_argument(
        "--channel",
        default="telegram",
        help="Default binding channel. Use 'none' to skip bindings.",
    )
    parser.add_argument(
        "--model-primary",
        default="moonshot/kimi-k2.5",
        help="Primary model identifier for the FlowHub agent",
    )
    parser.add_argument(
        "--plugin-source-path",
        default=str(PLUGIN_ROOT),
        help="Path used in the generated next-steps guide for plugin installation",
    )
    parser.add_argument(
        "--install-plugin",
        action="store_true",
        help="After writing the profile files, run `openclaw --profile <name> plugins install <plugin-path>`.",
    )
    parser.add_argument(
        "--openclaw-command",
        default="openclaw",
        help=(
            "Command used when --install-plugin is set. "
            "Examples: `openclaw`, `cmd.exe /C openclaw`, `/bin/echo`."
        ),
    )
    parser.add_argument(
        "--validate-profile",
        action="store_true",
        help="Run `openclaw --profile <name> config validate` after bootstrap.",
    )
    parser.add_argument(
        "--check-plugins",
        action="store_true",
        help="Run `openclaw --profile <name> plugins list` after bootstrap.",
    )
    parser.add_argument(
        "--start-gateway-service",
        action="store_true",
        help="Run `openclaw --profile <name> gateway start` after bootstrap.",
    )
    parser.add_argument(
        "--gateway-health-check",
        action="store_true",
        help="Run `openclaw --profile <name> gateway health` after bootstrap.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run a first-contact agent smoke test after bootstrap.",
    )
    parser.add_argument(
        "--smoke-test-to",
        default="+15550004444",
        help="Recipient used for the optional smoke test.",
    )
    parser.add_argument(
        "--smoke-test-message",
        default="你好，第一次使用 FlowHub，请先介绍一下项目、主要功能、相关插件和技能清单，并告诉我怎么安装。",
        help="Message sent when --smoke-test is enabled.",
    )
    parser.add_argument(
        "--run-gateway-foreground",
        action="store_true",
        help="After bootstrap, call the FlowHub gateway helper and run `gateway run` in the foreground.",
    )
    parser.add_argument(
        "--run-gateway-print-only",
        action="store_true",
        help="When used with --run-gateway-foreground, print the resolved gateway command instead of running it.",
    )
    parser.add_argument(
        "--gateway-run-force",
        action="store_true",
        help="When used with --run-gateway-foreground, pass --force to `gateway run`.",
    )
    parser.add_argument(
        "--gateway-run-verbose",
        action="store_true",
        help="When used with --run-gateway-foreground, pass --verbose to `gateway run`.",
    )
    parser.add_argument(
        "--gateway-run-claude-cli-logs",
        action="store_true",
        help="When used with --run-gateway-foreground, pass --claude-cli-logs to `gateway run`.",
    )
    parser.add_argument(
        "--gateway-run-compact",
        action="store_true",
        help="When used with --run-gateway-foreground, pass --compact to `gateway run`.",
    )
    parser.add_argument(
        "--write-next-steps",
        action="store_true",
        default=True,
        help="Write FLOWHUB_BOOTSTRAP_NEXT_STEPS.md into the profile directory",
    )
    return parser


def render_config(args: argparse.Namespace) -> dict:
    sample_path = LOCAL_SAMPLE if args.mode == "local" else VPS_SAMPLE
    config = load_json(sample_path)

    profile_dir = Path(args.profile_dir).expanduser()
    workspace_dir = Path(args.workspace_dir).expanduser()
    api_base_url = args.api_base_url or (
        "http://127.0.0.1:8000/api/v1" if args.mode == "local" else "https://your-flowhub-domain.example.com/api/v1"
    )
    gateway_token = args.gateway_token or secrets.token_hex(24)

    config.setdefault("agents", {})
    config["agents"]["list"] = [
        {
            "id": args.agent_id,
            "name": args.agent_name,
            "workspace": str(workspace_dir),
            "tools": {"allow": ["flowhub-openclaw"]},
        }
    ]
    config["agents"].setdefault("defaults", {})
    config["agents"]["defaults"].setdefault("model", {})
    config["agents"]["defaults"]["model"]["primary"] = args.model_primary

    config.setdefault("tools", {})
    config["tools"]["allow"] = ["flowhub-openclaw"]

    config.setdefault("gateway", {})
    config["gateway"]["mode"] = "local"
    config["gateway"]["bind"] = "loopback"
    config["gateway"]["port"] = args.gateway_port
    config["gateway"]["auth"] = {"mode": "token", "token": gateway_token}

    config.setdefault("plugins", {})
    config["plugins"]["allow"] = ["flowhub-openclaw"]
    config["plugins"]["entries"] = {
        "flowhub-openclaw": {
            "enabled": True,
            "config": {
                "apiBaseUrl": api_base_url,
                "apiKey": args.api_key,
                "timeoutMs": 20000,
                "defaultExecutionMode": "remote",
                "defaultOutputFormat": "markdown",
            },
        }
    }

    channel = str(args.channel or "").strip().lower()
    if channel and channel != "none":
        config["bindings"] = [{"match": {"channel": channel}, "agentId": args.agent_id}]
    else:
        config.pop("bindings", None)

    config.setdefault("commands", {})
    config["commands"].update(
        {
            "native": "auto",
            "nativeSkills": "auto",
            "restart": True,
            "ownerDisplay": "raw",
        }
    )

    profile_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    return config


def render_preinstall_config(config: dict) -> dict:
    """Return a temporary config that stays valid before the plugin is installed."""
    bootstrap_config = json.loads(json.dumps(config))

    tools = bootstrap_config.get("tools")
    if isinstance(tools, dict):
        tools.pop("allow", None)
        if not tools:
            bootstrap_config.pop("tools", None)

    agents = bootstrap_config.get("agents", {}).get("list", [])
    for agent in agents:
        if isinstance(agent, dict):
            agent_tools = agent.get("tools")
            if isinstance(agent_tools, dict):
                agent_tools.pop("allow", None)
                if not agent_tools:
                    agent.pop("tools", None)

    plugins = bootstrap_config.get("plugins")
    if isinstance(plugins, dict):
        plugins.pop("allow", None)
        plugins.pop("entries", None)
        if not plugins:
            bootstrap_config.pop("plugins", None)

    return bootstrap_config


def write_config(profile_dir: Path, config: dict) -> None:
    (profile_dir / "openclaw.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def render_next_steps(args: argparse.Namespace, profile_name: str, api_base_url: str) -> str:
    plugin_source = str(Path(args.plugin_source_path).expanduser())
    gateway_helper = str(PLUGIN_ROOT / "scripts" / "run_openclaw_flowhub_gateway.py")
    smoke_helper = str(PLUGIN_ROOT / "scripts" / "run_openclaw_flowhub_smoke.py")
    lines = [
        "# FlowHub OpenClaw Bootstrap Next Steps",
        "",
        "The bootstrap script created:",
        f"- profile directory: `{Path(args.profile_dir).expanduser()}`",
        f"- workspace directory: `{Path(args.workspace_dir).expanduser()}`",
        f"- gateway port: `{args.gateway_port}`",
        f"- FlowHub API: `{api_base_url}`",
        "",
        "## 1. Install or update the FlowHub plugin",
        "```bash",
        f"openclaw --profile {profile_name} plugins install {plugin_source}",
        "```",
        "",
        "## 2. Validate the profile",
        "```bash",
        f"openclaw --profile {profile_name} config validate",
        "```",
        "",
        "## 3. Start the gateway",
        "```bash",
        f"python3 {gateway_helper} --profile-dir {Path(args.profile_dir).expanduser()}",
        "```",
        "",
        "If OpenClaw must be invoked through Windows cmd:",
        "```bash",
        f"python3 {gateway_helper} --profile-dir {Path(args.profile_dir).expanduser()} --openclaw-command \"cmd.exe /C openclaw\"",
        "```",
        "",
        "## 4. Check gateway health",
        "```bash",
        f"openclaw --profile {profile_name} gateway health",
        "```",
        "",
        "## 5. First-contact verification",
        "```bash",
        f"python3 {smoke_helper} --profile-dir {Path(args.profile_dir).expanduser()} --agent-id {args.agent_id}",
        "```",
        "",
        "Expected result:",
        "- The agent should call `flowhub_handle_message` first",
        "- The reply should include project introduction, related components, and install guidance",
        "- It should not create a workflow just for onboarding",
        "",
        "## 6. Planning verification",
        "```bash",
        f"openclaw --profile {profile_name} agent --agent {args.agent_id} --to +15550004444 --message \"请使用 FlowHub 平台为我规划一个工作流：分析 AAPL 最近三个月走势，并返回 markdown 摘要。\" --json",
        "```",
    ]
    return "\n".join(lines) + "\n"


def command_tokens(command: str) -> list[str]:
    tokens = shlex.split(command)
    if not tokens:
        raise ValueError("openclaw command is empty")
    return tokens


def maybe_convert_path_for_command(path: PathLike[str] | str, command: list[str]) -> str:
    raw = str(path)
    exe = Path(command[0]).name.lower()
    is_windows_shell = exe in {"cmd.exe", "cmd", "powershell.exe", "powershell"}
    if not is_windows_shell:
        return raw
    try:
        converted = subprocess.run(
            ["wslpath", "-w", raw],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return converted or raw
    except Exception:
        return raw


def install_plugin(args: argparse.Namespace, profile_name: str) -> None:
    command = command_tokens(args.openclaw_command)
    plugin_source = maybe_convert_path_for_command(Path(args.plugin_source_path).expanduser(), command)
    full_command = [
        *command,
        "--profile",
        profile_name,
        "plugins",
        "install",
        plugin_source,
    ]
    print("plugin install command:", " ".join(shlex.quote(part) for part in full_command))
    subprocess.run(full_command, check=True)


def run_openclaw_command(args: argparse.Namespace, profile_name: str, *subcommand: str) -> None:
    command = command_tokens(args.openclaw_command)
    full_command = [*command, "--profile", profile_name, *subcommand]
    print("openclaw command:", " ".join(shlex.quote(part) for part in full_command))
    subprocess.run(full_command, check=True)


def run_gateway_helper(args: argparse.Namespace) -> None:
    helper_path = PLUGIN_ROOT / "scripts" / "run_openclaw_flowhub_gateway.py"
    full_command = [
        sys.executable,
        str(helper_path),
        "--profile-dir",
        str(Path(args.profile_dir).expanduser()),
        "--openclaw-command",
        args.openclaw_command,
    ]
    if args.gateway_run_force:
        full_command.append("--force")
    if args.gateway_run_verbose:
        full_command.append("--verbose")
    if args.gateway_run_claude_cli_logs:
        full_command.append("--claude-cli-logs")
    if args.gateway_run_compact:
        full_command.append("--compact")
    if args.run_gateway_print_only:
        full_command.append("--print-only")

    print("gateway helper command:", " ".join(shlex.quote(part) for part in full_command))
    subprocess.run(full_command, check=True)


def run_smoke_helper(args: argparse.Namespace) -> None:
    helper_path = PLUGIN_ROOT / "scripts" / "run_openclaw_flowhub_smoke.py"
    full_command = [
        sys.executable,
        str(helper_path),
        "--profile-dir",
        str(Path(args.profile_dir).expanduser()),
        "--agent-id",
        args.agent_id,
        "--openclaw-command",
        args.openclaw_command,
        "--to",
        args.smoke_test_to,
        "--message",
        args.smoke_test_message,
    ]
    print("smoke helper command:", " ".join(shlex.quote(part) for part in full_command))
    subprocess.run(full_command, check=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir).expanduser()
    workspace_dir = Path(args.workspace_dir).expanduser()
    profile_name = infer_profile_name(profile_dir)
    config = render_config(args)
    api_base_url = config["plugins"]["entries"]["flowhub-openclaw"]["config"]["apiBaseUrl"]

    if args.install_plugin:
        write_config(profile_dir, render_preinstall_config(config))
    else:
        write_config(profile_dir, config)
    (workspace_dir / "AGENTS.md").write_text(
        WORKSPACE_AGENTS_SAMPLE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    if args.write_next_steps:
        (profile_dir / "FLOWHUB_BOOTSTRAP_NEXT_STEPS.md").write_text(
            render_next_steps(args, profile_name, api_base_url),
            encoding="utf-8",
        )

    if args.install_plugin:
        install_plugin(args, profile_name)
        write_config(profile_dir, config)

    if args.validate_profile:
        run_openclaw_command(args, profile_name, "config", "validate")
    if args.check_plugins:
        run_openclaw_command(args, profile_name, "plugins", "list")
    if args.start_gateway_service:
        run_openclaw_command(args, profile_name, "gateway", "start")
    if args.gateway_health_check:
        run_openclaw_command(args, profile_name, "gateway", "health")
    if args.smoke_test:
        run_smoke_helper(args)
    if args.run_gateway_foreground:
        run_gateway_helper(args)

    print(f"FlowHub OpenClaw bootstrap completed for profile: {profile_name}")
    print(f"openclaw.json: {profile_dir / 'openclaw.json'}")
    print(f"workspace AGENTS: {workspace_dir / 'AGENTS.md'}")
    if args.write_next_steps:
        print(f"next steps: {profile_dir / 'FLOWHUB_BOOTSTRAP_NEXT_STEPS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
