#!/bin/bash
# E0 v2 confirmatory chain (frozen in docs/e0-v2-design-2026-09-03.md). CPU only.
cd /mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory
export CUDA_VISIBLE_DEVICES="" E0V2_PYLIB=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/13f60868-d8dd-4710-a6b1-3e9722fdb6db/scratchpad/pylib MPLCONFIGDIR=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/13f60868-d8dd-4710-a6b1-3e9722fdb6db/scratchpad/mpl NUMBA_CACHE_DIR=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/13f60868-d8dd-4710-a6b1-3e9722fdb6db/scratchpad/numba XDG_CACHE_HOME=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/claude_persist/tmp/claude-20043/-mnt-cpfs-epic-user-yangboxue-20260612-opsd-Memory/13f60868-d8dd-4710-a6b1-3e9722fdb6db/scratchpad/cache
export TORCHINDUCTOR_CACHE_DIR=/mnt/cpfs/epic-user/yangboxue-20260612/opsd/Memory/.tmp/torchinductor
P="python3 -u code/e0v2/run.py --lambda_scale 0.5 --threads 2"
$P --exp e0a --seeds 0 1 2 3 4 --workers 5
$P --exp e0a --seeds 0 1 2 3 4 --arms regime_grace --workers 5 --lambda_scale 0.25 --tag _lam025
$P --exp e0a --seeds 0 1 2 3 4 --arms regime_grace --workers 5 --lambda_scale 1.0 --tag _lam100
$P --exp e0a_lag2 --seeds 0 1 2 3 4 --workers 5
$P --exp e0b --seeds 0 1 2 3 4 --sigmas 0.01 --workers 6
$P --exp e0c_mlp --seeds 0 1 2 3 4 --sigmas 0.01 --workers 5
$P --exp e0c --seeds 0 1 2 --sigmas 0.01 --workers 3
echo CHAIN_DONE
