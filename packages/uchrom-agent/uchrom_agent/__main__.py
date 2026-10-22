"""Command-line entrypoint for the U-Chrom companion."""

from __future__ import annotations

import argparse
import sys

from .client_config import configure_client
from .mcp_stdio import serve


def _parser():
    parser = argparse.ArgumentParser(prog="uchrom-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="run the stdio MCP server")
    setup = commands.add_parser("setup", help="preview or write a Claude Code or Codex MCP entry")
    setup.add_argument("client", choices=("claude", "codex"))
    setup.add_argument("--config", required=True, metavar="PATH",
                       help="explicit client config path (Claude Code: inspect `claude mcp list`; Codex: open config.toml from Codex Settings)")
    setup.add_argument("--command", default="uchrom-agent",
                       help="uchrom-agent executable to launch (default: PATH lookup)")
    setup.add_argument("--write", action="store_true", help="back up and atomically write the config; default is preview only")
    return parser


def _cli():
    args = _parser().parse_args()
    if args.command == "mcp":
        serve()
        return
    try:
        diff = configure_client(args.client, args.config, command=args.command, write=args.write)
    except (OSError, ValueError) as exc:
        print(f"uchrom-agent: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    sys.stdout.write(diff)


if __name__ == "__main__":
    _cli()
