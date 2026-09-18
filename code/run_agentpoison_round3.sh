#!/usr/bin/env bash
# P3-B AgentPoison round 3: freeze the protocol, then run it (docs/p3b-round3-protocol-2026-09-03.md §7).
set -euo pipefail
ROOT=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
cd "$ROOT"
export HF_HOME=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/hf_home HF_HUB_CACHE=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/hf_home/hub \
       TRANSFORMERS_CACHE=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/hf_home/hub HF_HUB_OFFLINE=1 \
       TMPDIR=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/torch_tmp \
       TORCHINDUCTOR_CACHE_DIR=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/torchinductor \
       XDG_CACHE_HOME=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/torch_tmp OMP_NUM_THREADS=4
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy ALL_PROXY all_proxy || true
OUT=results/real/p3b_round3/agentpoison
ARGS=(--backend openai --model deepseek-chat --device cpu --temperature 0 --max-tokens 1024 --max-steps 7
      --calibration-ids $(seq 0 31) --calibration-replicates 2
      --seed-blocks 0:124:147 1:148:171 2:172:195 3:196:219 --test-replicates 3 --utility-replicates 1
      --driver-threshold 0.20 --driver-min-retrievals 2 --temporal-ancestry-hops 1 --cluster-k 2 --cluster-cosine-threshold 0.8
      --protocol-document docs/p3b-round3-protocol-2026-09-03.md --out $OUT/agentpoison_r3_gate.json)
if [ ! -f $OUT/frozen_protocol.json ]; then
  python3 code/agentpoison_strategyqa_gate.py "${ARGS[@]}" --freeze-protocol-only --protocol-out $OUT/frozen_protocol.json
fi
exec python3 code/run_with_local_deepseek.py --key-file /mnt/cpfs/epic-user/yangboxue-20260612/opsd/deepseek_apikey.md -- \
     python3 code/agentpoison_strategyqa_gate.py "${ARGS[@]}" --frozen-protocol $OUT/frozen_protocol.json --verbose "$@"
