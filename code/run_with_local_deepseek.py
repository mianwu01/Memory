"""Execute a command with the ignored local DeepSeek credential.

The credential is read into the child environment and is never printed, copied
to argv, or written to a result file.  This helper exists so detached experiment
commands do not need shell interpolation that could accidentally expose a key.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", default=str(ROOT / "deepseek_apikey.md"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    text = Path(args.key_file).read_text()
    match = re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", text)
    if not match:
        raise SystemExit("local key file does not contain a recognizable credential")
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = match.group(0)
    environment.setdefault("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    environment.setdefault("OPENAI_API_BASE", "https://api.deepseek.com/v1")
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
