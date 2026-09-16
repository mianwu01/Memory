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
DEFAULT_BASE_URL = "https://bboluo.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
KEY_PATTERN = r"(?:sk_tr_|sk-|bo-)[A-Za-z0-9_-]{16,}"


def local_environment(key_file: str | Path, base_url: str | None = None,
                      model: str | None = None) -> dict[str, str]:
    """Load the local credential and its paired route without exposing either key."""
    text = Path(key_file).read_text()
    # Prefer an explicit API key over incidental credentials in legacy prose.
    # A provider's sess_ token is never an API key.
    assignment = re.search(r"(?m)^(?:OPENAI_API_KEY|DEEPSEEK_API_KEY)\s*=\s*(\S+)\s*$", text)
    match = (re.fullmatch(KEY_PATTERN, assignment.group(1)) if assignment else
             re.search(r"\b" + KEY_PATTERN + r"\b", text))
    if not match:
        raise ValueError("local key file does not contain a recognizable credential")
    configured_url = re.search(r"(?m)^OPENAI_BASE_URL\s*=\s*(https://\S+)\s*$", text)
    endpoint = (base_url or (configured_url.group(1) if configured_url else DEFAULT_BASE_URL)).rstrip("/")
    configured_model = re.search(r"(?m)^(?:OPENAI_MODEL|DEEPSEEK_MODEL)\s*=\s*(\S+)\s*$", text)
    selected_model = model or (configured_model.group(1) if configured_model else DEFAULT_MODEL)
    environment = os.environ.copy()
    # Keep the credential and endpoint paired, even if an old route is inherited.
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        environment[name] = match.group(0)
    for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "DEEPSEEK_BASE_URL"):
        environment[name] = endpoint
    for name in ("OPENAI_MODEL", "DEEPSEEK_MODEL"):
        environment[name] = selected_model
    return environment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", default=str(ROOT / "deepseek_apikey.md"))
    parser.add_argument("--base-url", help="override the endpoint paired with the local key")
    parser.add_argument("--model", help="override the model paired with the local route")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        parser.error("a command is required after --")

    try:
        environment = local_environment(args.key_file, args.base_url, args.model)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    os.execvpe(command[0], command, environment)


if __name__ == "__main__":
    main()
