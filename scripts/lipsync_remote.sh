#!/bin/zsh
# Drive the LatentSync lip-sync pass on the remote 4090 over ssh.
#   REMOTE=user@host zsh scripts/lipsync_remote.sh setup
#   REMOTE=user@host zsh scripts/lipsync_remote.sh run outputs/songs/so-i-die/clips/lipsync/sid_r3_esc_film2 [more takes...]
#   REMOTE=user@host zsh scripts/lipsync_remote.sh all          # the 7 so I die + Playboi takes, then both cuts
# Per take: uploads <take>_mux.mp4 + clip.wav, runs inference on the GPU, downloads the synced mp4 to
# <take>/<TAG>/<take>_<TAG>.mp4, lays mux.wav (song window) over it -> <take>/<TAG>/<take>_<TAG>_mux.mp4, scores + compares.
# Env: RDIR (remote dir, default ~/lipsync), TAG (default latentsync), STEPS 20, GUIDANCE 1.5, SEED 1247, FPS 24,
#      COMFY (remote ComfyUI URL, default http://100.104.17.103:8188; its models are unloaded before each job so the
#      18 GB LatentSync 1.6 needs fit next to it; it waits for the shared queue to be empty first).
set -e -o pipefail
cd "$(dirname "$0")/.."
REMOTE=${REMOTE:?set REMOTE=user@host}
RDIR=${RDIR:-'~/lipsync'}
TAG=${TAG:-latentsync}; STEPS=${STEPS:-20}; GUIDANCE=${GUIDANCE:-1.5}; SEED=${SEED:-1247}; FPS=${FPS:-24}
COMFY=${COMFY:-http://100.104.17.103:8188}
PY=~/dev/lipsync/.venv/bin/python   # local venv (mediapipe sync check, compare sheet)
SID=(sid_r3_esc_film2 sid_r4_glance_film sid_r4_esc2_film sid_r4_esc3_film sid_r4_glance2_film)
PB=(pb_g_booth_hook pb_g_motel_play)

setup() {
  scp -q ~/dev/lipsync/latentsync_mps.patch "$REMOTE:$RDIR/latentsync.patch" 2>/dev/null || { ssh "$REMOTE" "mkdir -p $RDIR"; scp -q ~/dev/lipsync/latentsync_mps.patch "$REMOTE:$RDIR/latentsync.patch"; }
  ssh "$REMOTE" "RDIR=$RDIR bash -s" < scripts/lipsync_remote_setup.sh
}

wait_idle() {  # don't fight other agents' H3 jobs for the GPU
  while true; do
    n=$(curl -s -m 10 "$COMFY/queue" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['queue_running'])+len(d['queue_pending']))" 2>/dev/null || echo 0)
    [[ "$n" == "0" ]] && break
    echo "  remote ComfyUI busy ($n jobs), waiting"; sleep 15
  done
  curl -s -m 10 -X POST "$COMFY/free" -H 'content-type: application/json' -d '{"unload_models":true,"free_memory":true}' >/dev/null || true
}

run_take() {
  local take=$1; local name=$(basename "$take")
  local out=$take/$TAG; mkdir -p "$out"
  if [[ -f $out/${name}_${TAG}_mux.mp4 ]]; then echo "== $name: already done ($TAG)"; return; fi
  echo "== $name ($(date +%H:%M))"
  ffmpeg -v error -y -i "$take/clip.wav" -ac 1 -ar 16000 "$out/drive.wav"
  ssh "$REMOTE" "mkdir -p $RDIR/jobs/$name"
  scp -q "$take/${name}_mux.mp4" "$out/drive.wav" "$REMOTE:$RDIR/jobs/$name/"
  wait_idle
  local t0=$(date +%s)
  ssh "$REMOTE" "cd $RDIR/LatentSync && PYTHONUNBUFFERED=1 .venv/bin/python -m scripts.inference \
      --unet_config_path configs/unet/stage2_512.yaml --inference_ckpt_path checkpoints/latentsync_unet.pt \
      --inference_steps $STEPS --guidance_scale $GUIDANCE --seed $SEED --fps $FPS \
      --video_path $RDIR/jobs/$name/${name}_mux.mp4 --audio_path $RDIR/jobs/$name/drive.wav \
      --video_out_path $RDIR/jobs/$name/${name}_${TAG}.mp4 --temp_dir $RDIR/jobs/$name/tmp 2>&1 | grep -v 'it/s\]\|s/it\]'"
  scp -q "$REMOTE:$RDIR/jobs/$name/${name}_${TAG}.mp4" "$out/"
  ssh "$REMOTE" "rm -rf $RDIR/jobs/$name/tmp $RDIR/jobs/$name/${name}_mux.mp4"
  ffmpeg -v error -y -i "$out/${name}_${TAG}.mp4" -i "$take/mux.wav" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest "$out/${name}_${TAG}_mux.mp4"
  python3 - "$out" "$take" "$TAG" $STEPS $GUIDANCE $SEED $(( $(date +%s) - t0 )) <<'EOF'
import json, sys
out, take, tag, steps, guidance, seed, secs = sys.argv[1:]
json.dump({"engine": "latentsync-1.6 (remote 4090)", "take": take, "tag": tag, "steps": int(steps), "guidance": float(guidance),
           "seed": int(seed), "seconds": int(secs), "mux": f"{out}/{take.rstrip('/').split('/')[-1]}_{tag}_mux.mp4"}, open(f"{out}/run.json", "w"), indent=2)
EOF
  echo "   $(( $(date +%s) - t0 )) s -> $out/${name}_${TAG}_mux.mp4"
  [[ -x $PY ]] && $PY scripts/h3_sync_check.py --video "$out/${name}_${TAG}_mux.mp4" --vocal "$take/clip.wav" --model ~/dev/lipsync/face_landmarker.task --plot "$out/sync.png" 2>/dev/null | grep -E "r_level_lag0|r_level_best|best_lag_ms_level" || true
  [[ -x $PY ]] && $PY scripts/qa/lipsync_compare.py "$take" "$TAG" >/dev/null 2>&1 || true
}

case ${1:-} in
  setup) setup ;;
  run) shift; for t in "$@"; do run_take "$t"; done ;;
  all)
    for t in $SID; do run_take outputs/songs/so-i-die/clips/lipsync/$t; done
    python3 scripts/content/songs_cut.py so-i-die E F --tag $TAG
    for t in $PB; do run_take outputs/songs/playboi/clips/lipsync/$t; done
    python3 scripts/content/songs_cut.py playboi v6 --tag $TAG
    echo "done $(date +%H:%M)"
    ls -1 outputs/songs/so-i-die/edit_v5/*_$TAG/*_review.mp4 outputs/songs/playboi/edit_v6_$TAG/*_review.mp4 ;;
  *) echo "usage: REMOTE=user@host $0 setup | run <take_dir>... | all"; exit 1 ;;
esac
