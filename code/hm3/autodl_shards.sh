#!/bin/bash
# Launch HM3 LLM shards on the AutoDL endpoint, one API key per shard, round-robin over api/api.txt.
# usage: bash code/hm3/autodl_shards.sh <out_root> <domain> <history> <n_eval> <shard_size> <budget_per_shard> <selections...>
# example: bash code/hm3/autodl_shards.sh results/real/hm3/scaling/travel_500 travel 500:abcd 64 16 3.0 graph_closed full bm25_k16
set -u
ROOT=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
# PYLIB may be overridden (or set empty) for machines whose system Python already has the packages (session B: 3.12)
PYLIB=${PYLIB-/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/aa111f6d-b918-45ce-bc18-326170fa9a1b/scratchpad/pylib2}
OUT=$1; DOMAIN=$2; HIST=$3; NEVAL=$4; SHARD=$5; BUDGET=$6; shift 6; SELS="$@"
MODEL=${MODEL:-deepseek-v4-flash}
SEED=${SEED:-30}
SERS=${SERS:-compact verbose}
SELHIST=${SELHIST:-}
SHARDSUB=${SHARDSUB:-shards}
PROMPT=${PROMPT:-v2}
mapfile -t ALLKEYS < <(grep -v '^\s*$' $ROOT/api/api.txt)
# KEYIDX="0 1" restricts this launch to a subset of the keys (so two sessions can split them)
if [ -n "${KEYIDX:-}" ]; then KEYS=(); for k in $KEYIDX; do KEYS+=("${ALLKEYS[$k]}"); done; else KEYS=("${ALLKEYS[@]}"); fi
MAXTOK=${MAXTOK:-}
NK=${#KEYS[@]}
i=0
for ((s=0; s<NEVAL; s+=SHARD)); do
  e=$((s+SHARD)); [ $e -gt $NEVAL ] && e=$NEVAL
  key=${KEYS[$((i % NK))]}; i=$((i+1))
  dir=$OUT/$SHARDSUB/${DOMAIN}_${s}_${e}
  mkdir -p $dir
  (cd $ROOT/code && OMP_NUM_THREADS=${OMP_NUM_THREADS:-2} OPENAI_API_KEY="$key" OPENAI_BASE_URL=https://www.autodl.art/api/v1 PYTHONPATH=${PYLIB:+$PYLIB:}. \
    nohup python3 -m hm3.llm --domains $DOMAIN --seed $SEED --n_eval $NEVAL --ep_start $s --ep_end $e \
      --selections $SELS --serializations $SERS --model $MODEL --prompt $PROMPT --history $HIST \
      --out_dir $ROOT/$dir --budget_usd $BUDGET ${SELHIST:+--selector_history $SELHIST} ${MAXTOK:+--max_tokens $MAXTOK} > $ROOT/$dir/shard.log 2>&1 &)
  echo "shard $dir key#$((i % NK)) pid $!"
done
