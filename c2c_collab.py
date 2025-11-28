#!/usr/bin/env python3
"""
C2C Collaboration Daemon

Launches Claude Code with the C2C Bridge, enabling remote collaboration.
The session auto-shuts down after idle timeout.

Usage:
    python c2c_collab.py --name my-machine

This will:
1. Start the C2C Bridge server
2. Launch Claude Code in permissive mode with the bridge as MCP server
3. Auto-shutdown when idle (default 15 minutes)
4. Shutdown when remote requests it via c2c_end_session()
"""

import argparse
import asyncio
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# Add the project to path if running directly
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Start a C2C collaboration session with Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Start a collaboration session in current directory:
    python c2c_collab.py --name my-workstation

  Start in a specific directory:
    python c2c_collab.py --name my-workstation --directory /path/to/project

  With custom idle timeout (30 minutes):
    python c2c_collab.py --name my-workstation --idle-timeout 1800

  With custom port:
    python c2c_collab.py --name my-workstation --port 9443

After starting:
1. Copy the credentials/ folder to the connecting machine
2. Configure Claude Code on that machine to connect to the displayed URL
3. Return to the other machine and collaborate remotely

The session will auto-shutdown after the idle timeout, or when the
remote instance calls c2c_end_session().
        """
    )

    parser.add_argument(
        "--name", "-n",
        default=None,
        help="Name for this machine (default: hostname)"
    )

    parser.add_argument(
        "--directory", "-d",
        type=Path,
        default=None,
        help="Working directory for Claude Code (default: current directory)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8443,
        help="Port for the bridge server (default: 8443)"
    )

    parser.add_argument(
        "--idle-timeout", "-t",
        type=int,
        default=900,
        help="Seconds before auto-shutdown when idle (default: 900 = 15 min)"
    )

    parser.add_argument(
        "--credentials-dir",
        type=Path,
        default=None,
        help="Directory for credentials (default: <c2c_bridge>/credentials)"
    )

    parser.add_argument(
        "--bridge-only",
        action="store_true",
        help="Only start the bridge server, don't launch Claude Code"
    )

    return parser.parse_args()


def find_claude_command():
    """Find the claude command."""
    # Check if claude is in PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    # Common locations
    common_paths = [
        Path.home() / ".claude" / "local" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/usr/bin/claude"),
    ]

    for path in common_paths:
        if path.exists() and path.is_file():
            return str(path)

    return None


def print_banner(name: str, idle_timeout: int, working_dir: Path, bridge_only: bool):
    """Print startup banner."""
    print()
    print("=" * 60)
    print("  C2C Collaboration Session")
    print("=" * 60)
    print()
    print(f"  Machine: {name}")
    print(f"  Working directory: {working_dir}")
    print(f"  Idle timeout: {idle_timeout // 60} minutes")
    if bridge_only:
        print(f"  Mode: Bridge only (Claude Code not started)")
    else:
        print(f"  Mode: Full (Claude Code + Bridge)")
    print()
    print("  This window indicates an active collaboration session.")
    print("  Close this window or press Ctrl+C to end the session.")
    print()
    print("=" * 60)
    print()


async def run_bridge_server(settings_dict):
    """Run the bridge server."""
    from c2c_bridge.server import C2CServer
    from c2c_bridge.config import Settings

    settings = Settings(**settings_dict)
    server = C2CServer(settings)
    await server.run_server()


def create_mcp_config(bridge_script: Path, name: str, port: int,
                       credentials_dir: Path, idle_timeout: int) -> dict:
    """Create MCP configuration for Claude Code.

    Uses hybrid mode so the bridge:
    - Communicates with local Claude Code via stdio (MCP)
    - Accepts remote connections via HTTPS
    """
    return {
        "mcpServers": {
            "c2c-bridge": {
                "command": sys.executable,
                "args": [
                    "-m", "c2c_bridge.server",
                    "--name", name,
                    "--mode", "hybrid",  # Both stdio MCP + HTTPS server
                    "--port", str(port),
                    "--credentials-dir", str(credentials_dir),
                    "--auto-shutdown", str(idle_timeout),
                ],
                "cwd": str(bridge_script.parent),
            }
        }
    }


async def run_full_session(args, working_dir: Path, credentials_dir: Path):
    """Run Claude Code with the bridge as MCP server."""

    claude_cmd = find_claude_command()
    if not claude_cmd:
        print("Error: Could not find 'claude' command.", file=sys.stderr)
        print("Make sure Claude Code is installed and in your PATH.", file=sys.stderr)
        return 1

    # Create temporary MCP config
    mcp_config = create_mcp_config(
        project_root,
        args.name,
        args.port,
        credentials_dir,
        args.idle_timeout,
    )

    # Write config to temp file
    config_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        prefix='c2c_mcp_',
        delete=False
    )
    json.dump(mcp_config, config_file)
    config_file.close()

    try:
        # Build claude command
        cmd = [
            claude_cmd,
            "--dangerously-skip-permissions",
            "--mcp-config", config_file.name,
        ]

        print(f"Starting Claude Code in: {working_dir}")
        print(f"With MCP config: {config_file.name}")
        print()

        # Run Claude Code
        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        # Wait for process to complete
        return process.wait()

    finally:
        # Clean up temp config
        try:
            os.unlink(config_file.name)
        except:
            pass


async def run_bridge_only(args, credentials_dir: Path):
    """Run only the bridge server."""
    settings_dict = {
        "instance_name": args.name,
        "mode": "server",
        "port": args.port,
        "auto_shutdown_idle": args.idle_timeout,
        "credentials_dir": credentials_dir,
    }

    await run_bridge_server(settings_dict)
    return 0


def main():
    """Main entry point."""
    args = parse_args()

    # Default name to hostname
    if args.name is None:
        args.name = platform.node() or "unnamed"

    # Determine working directory
    working_dir = args.directory or Path.cwd()
    working_dir = working_dir.resolve()

    if not working_dir.exists():
        print(f"Error: Directory does not exist: {working_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine credentials directory
    credentials_dir = args.credentials_dir or (project_root / "credentials")
    credentials_dir = credentials_dir.resolve()

    print_banner(args.name, args.idle_timeout, working_dir, args.bridge_only)

    try:
        if args.bridge_only:
            exit_code = asyncio.run(run_bridge_only(args, credentials_dir))
        else:
            exit_code = asyncio.run(run_full_session(args, working_dir, credentials_dir))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nSession ended by user (Ctrl+C)")
        sys.exit(0)


if __name__ == "__main__":
    main()
