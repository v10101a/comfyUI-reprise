#!/bin/zsh
# sheet.sh <video> <out.jpg> [n=8] [cols=4] [width=480]  -- evenly spaced contact sheet with timestamps
set -e
v=$1; out=$2; n=${3:-8}; cols=${4:-4}; w=${5:-480}
F=/opt/homebrew/bin/ffmpeg
dur=$(/opt/homebrew/bin/ffprobe -v error -show_entries format=duration -of csv=p=0 "$v")
tmp=$(mktemp -d)
for i in $(seq 0 $((n-1))); do
  t=$(python3 -c "print(round($dur*($i+0.5)/$n,2))")
  $F -v error -ss $t -i "$v" -frames:v 1 -vf "scale=$w:-2" $tmp/f_$(printf %03d $i).png
done
rows=$(( (n+cols-1)/cols ))
$F -v error -y -i $tmp/f_%03d.png -vf "tile=${cols}x${rows}:padding=4" -frames:v 1 -q:v 3 "$out"
rm -rf $tmp
echo "$out"
