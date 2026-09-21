#!/bin/bash
# Launch the substrate-port actor panel (hm3.arena_run) as one process per shard.  Each shard runs its
# stages sequentially: prompt v1 (cheap systems) -> prompt v2 -> A-Mem v1 -> A-Mem v2 (A-Mem only when
# AMEM=yes), so the per-shard selection cache is never written by two processes at once.
# usage: bash code/hm3/arena_shards.sh <domain> <history> <n_eval> <shard_size> <out_root> [systems...]
#   env: KEYIDX="0 1" (keys, round-robin), AMEM=yes|no, PROMPTS="v1 v2", BUDGET=40, MODEL, MAXTOK
set -u
ROOT=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
PYLIB=${PYLIB-/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/aa111f6d-b918-45ce-bc18-326170fa9a1b/scratchpad/pylib2}
DOMAIN=$1; HIST=$2; NEVAL=$3; SHARD=$4; OUTROOT=$5; shift 5
[[ $OUTROOT != /* ]] && OUTROOT=$ROOT/$OUTROOT
SYSTEMS=${*:-"causal bm25 bm25_k16 long_context"}
AMEM=${AMEM:-no}; PROMPTS=${PROMPTS:-"v1 v2"}; BUDGET=${BUDGET:-40}; MODEL=${MODEL:-deepseek-v4-flash}; MAXTOK=${MAXTOK:-16384}; SEED=${SEED:-30}
mapfile -t ALLKEYS < <(grep -v '^\s*$' $ROOT/api/api.txt)
if [ -n "${KEYIDX:-}" ]; then KEYS=(); for k in $KEYIDX; do KEYS+=("${ALLKEYS[$k]}"); done; else KEYS=("${ALLKEYS[@]}"); fi
NK=${#KEYS[@]}; i=0
for ((s=0; s<NEVAL; s+=SHARD)); do
  e=$((s+SHARD)); [ $e -gt $NEVAL ] && e=$NEVAL
  key=${KEYS[$((i % NK))]}; i=$((i+1))
  base=$OUTROOT/shard_${s}_${e}; mkdir -p $base
  steps=""
  for P in $PROMPTS; do
    steps="$steps python3 -m hm3.arena_run --domain $DOMAIN --seed $SEED --n_eval $NEVAL --ep_start $s --ep_end $e --history $HIST --systems $SYSTEMS --prompt $P --model $MODEL --max_tokens $MAXTOK --budget_usd $BUDGET --out_dir $base/$P &&"
  done
  if [ "$AMEM" = yes ]; then
    for P in $PROMPTS; do
      steps="$steps python3 -m hm3.arena_run --domain $DOMAIN --seed $SEED --n_eval $NEVAL --ep_start $s --ep_end $e --history $HIST --systems amem --prompt $P --model $MODEL --max_tokens $MAXTOK --budget_usd $BUDGET --out_dir $base/$P &&"
    done
  fi
  steps="${steps% &&}"
  (cd $ROOT/code && OPENAI_API_KEY="$key" OPENAI_BASE_URL=https://www.autodl.art/api/v1 OMP_NUM_THREADS=2 \
     PYTHONPATH=${PYLIB:+$PYLIB:}$ROOT/benchmarks/A-mem:. nohup bash -c "$steps" > $base/chain.log 2>&1 &)
  echo "shard $base key#$(( (i-1) % NK ))"
done
