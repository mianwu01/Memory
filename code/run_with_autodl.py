"""Run an experiment with the ignored AutoDL credential, never placed in argv."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://www.autodl.art/api/v1"
MODEL = "DeepSeek-V4.1-Flash"


def environment():
    key = (ROOT / ".secrets/autodl_api_token").read_text().strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("Invalid local AutoDL credential")
    env = os.environ.copy()
    for name in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        env[name] = key
    for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "DEEPSEEK_BASE_URL"):
        env[name] = ENDPOINT
    for name in ("OPENAI_MODEL", "DEEPSEEK_MODEL"):
        env[name] = MODEL
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "2"
    env["CUDA_VISIBLE_DEVICES"] = ""
    env["HF_HUB_OFFLINE"] = "1"
    env["HF_DATASETS_OFFLINE"] = "1"
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("Expected a command after --")
    os.execvpe(command[0], command, environment())


if __name__ == "__main__":
    main()
