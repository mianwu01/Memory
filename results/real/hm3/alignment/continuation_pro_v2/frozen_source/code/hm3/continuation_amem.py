"""A-Mem pinned paper implementation with its missing stdlib import supplied.

No author algorithm/prompt change. Exact metadata requests from the invalid dev
attempt may be replayed; changed evolution requests require fresh responses.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

from . import continuation_memsys as native
from .continuation_actor import CONFIG, write_once
from .structure_alignment import digest


def cache_key(row):
    return digest([row.get(k) for k in ["model", "messages", "response_format", "temperature", "max_tokens"]])


def main(args):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    sys.path.insert(0, str(Path(args.source).resolve() / "benchmarks/AgenticMemory-paper"))
    import memory_layer
    memory_layer.re = re
    args.system = "amem"
    episodes = json.loads(Path(args.episodes).read_text())
    directory = Path(args.out) / "amem" / episodes[args.index]["id"]
    write_once(directory / "adapter_patch.json", {
        "patch": "supply missing Python stdlib re in author module namespace",
        "upstream_unchanged": True, "algorithm_or_prompt_changed": False,
        "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reuse_memory_calls": args.reuse_memory_calls})
    cache = {}
    if args.reuse_memory_calls:
        for line in Path(args.reuse_memory_calls).read_text().splitlines():
            r = json.loads(line)
            if r["event"] == "result":
                cache.setdefault(cache_key(r), r)
    original_meter = native.NativeMeter

    class CachedMeter(original_meter):
        def install(self):
            import openai
            from openai.types.chat import ChatCompletion
            parent = super().install()
            metered = openai.OpenAI
            meter = self

            class Cached(metered):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    measured = self.chat.completions.create

                    def create(*a, **kw):
                        key = cache_key({**kw, "max_tokens": 16384})
                        if key not in cache:
                            return measured(*a, **kw)
                        r = cache[key]
                        row = {**r, "reused_from": args.reuse_memory_calls,
                               "reuse_note": "exact model/messages/format/temperature/output budget; same thinking mode"}
                        with meter.lock:
                            with (meter.directory / "memory_calls.jsonl").open("a") as f:
                                f.write(json.dumps(row)+"\n")
                        return ChatCompletion(id="replay-"+key, object="chat.completion", created=int(time.time()),
                                              model=r["returned_model"], choices=r["choices"], usage=r["usage"])
                    self.chat.completions.create = create
            openai.OpenAI = Cached
            return parent
    native.NativeMeter = CachedMeter
    native.run(args)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=".tmp/continuation_deps")
    p.add_argument("--episodes", required=True)
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--out", required=True)
    p.add_argument("--key-file", default="api/api.txt")
    p.add_argument("--reuse-memory-calls")
    main(p.parse_args())
