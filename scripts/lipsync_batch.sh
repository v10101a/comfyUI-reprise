#!/bin/zsh
# Lip-sync pass for the so I die + Playboi takes, then rebuild both review cuts with the synced takes.
# Runs LatentSync 1.6 locally (Mac GPU, ~/dev/lipsync) one take at a time, scores each result against the vocal,
# and writes a side-by-side compare video per take.
#   zsh scripts/lipsync_batch.sh            # all 7 takes + cuts
#   zsh scripts/lipsync_batch.sh pb         # only the Playboi takes + Playboi cut
#   zsh scripts/lipsync_batch.sh sid        # only the so I die takes + so I die cuts
#   TAG=ls_g1 STEPS=20 GUIDANCE=1.0 zsh scripts/lipsync_batch.sh   # alt settings under another tag
set -e
cd "$(dirname "$0")/.."
PY=~/dev/lipsync/.venv/bin/python
TAG=${TAG:-latentsync}; STEPS=${STEPS:-20}; GUIDANCE=${GUIDANCE:-1.5}; SEED=${SEED:-1247}
SID=(sid_r3_esc_film2 sid_r4_glance_film sid_r4_esc2_film sid_r4_esc3_film sid_r4_glance2_film)
PB=(pb_g_booth_hook pb_g_motel_play)
which=${1:-all}

run_take() {  # $1 = song slug, $2 = take name
  local take=outputs/songs/$1/clips/lipsync/$2
  if [[ -f $take/$TAG/${2}_${TAG}_mux.mp4 ]]; then echo "== $2: already done ($TAG)"; return; fi
  echo "== $2 ($(date +%H:%M))"
  $PY scripts/lipsync_pass.py $take --engine latentsync --tag $TAG --steps $STEPS --guidance $GUIDANCE --seed $SEED
  $PY scripts/h3_sync_check.py --video $take/$TAG/${2}_${TAG}_mux.mp4 --vocal $take/clip.wav \
      --model ~/dev/lipsync/face_landmarker.task --plot $take/$TAG/sync.png || true
  $PY scripts/qa/lipsync_compare.py $take $TAG || true
}

if [[ $which == all || $which == sid ]]; then
  for t in $SID; do run_take so-i-die $t; done
  python3 scripts/content/songs_cut.py so-i-die E F --tag $TAG
fi
if [[ $which == all || $which == pb ]]; then
  for t in $PB; do run_take playboi $t; done
  python3 scripts/content/songs_cut.py playboi v6 --tag $TAG
fi
echo "done $(date +%H:%M)"
ls -1 outputs/songs/so-i-die/edit_v5/*_$TAG/*_review.mp4 outputs/songs/playboi/edit_v6_$TAG/*_review.mp4 2>/dev/null
