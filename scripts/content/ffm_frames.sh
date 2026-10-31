#!/bin/zsh
# ffm_frames.sh <tag> <frame>... -> composite frames via #/render (preview == export), tiled to outputs/ffm/iter/<tag>_frames.jpg
set -e
cd /Users/lh1783/dev/comfy; tag=$1; shift; pid=$(cat outputs/ffm/project_id.txt)
server/.venv/bin/python apps/web/scripts/verify_frames.py $pid ffm_$tag "$@" | grep -v '^/' || true
mkdir -p outputs/ffm/iter/$tag; mv apps/web/.verify/ffm_${tag}_f*.png outputs/ffm/iter/$tag/
n=$#; cols=${COLS:-4}; rows=$(( (n+cols-1)/cols ))
/opt/homebrew/bin/ffmpeg -v error -y -pattern_type glob -i "outputs/ffm/iter/$tag/ffm_${tag}_f*.png" -vf "scale=${W:-400}:-2,tile=${cols}x${rows}:padding=4" -frames:v 1 -q:v 3 outputs/ffm/iter/${tag}_frames.jpg
echo outputs/ffm/iter/${tag}_frames.jpg
