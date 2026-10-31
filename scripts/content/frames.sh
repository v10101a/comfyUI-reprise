#!/bin/zsh
# frames.sh <tag> <frame>... -> renders composite frames via #/render (preview == export) and tiles outputs/hero/iter/<tag>_frames.jpg
set -e
cd /Users/lh1783/dev/comfy; tag=$1; shift; pid=$(cat outputs/hero/project_id.txt)
server/.venv/bin/python apps/web/scripts/verify_frames.py $pid hero_$tag "$@" | grep -v '^/' || true
mkdir -p outputs/hero/iter/$tag; mv apps/web/.verify/hero_${tag}_f*.png outputs/hero/iter/$tag/
n=$#; cols=3; rows=$(( (n+cols-1)/cols ))
/opt/homebrew/bin/ffmpeg -v error -y -pattern_type glob -i "outputs/hero/iter/$tag/hero_${tag}_f*.png" -vf "scale=640:-2,tile=${cols}x${rows}:padding=4" -frames:v 1 -q:v 3 outputs/hero/iter/${tag}_frames.jpg
echo outputs/hero/iter/${tag}_frames.jpg
