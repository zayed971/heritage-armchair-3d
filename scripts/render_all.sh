#!/usr/bin/env bash
# Render every final still, one at a time. Safe to re-run: skips stills already newer than the model.
set -u
cd "$(dirname "$0")/.."
BLENDER="${BLENDER:-/c/Program Files/Blender Foundation/Blender 5.2/blender.exe}"
RES="${RES:-1600}"
SAMPLES="${SAMPLES:-110}"
mkdir -p out/final
for v in hero detail_back detail_arm high front back; do
  png="out/final/$v.png"
  if [ -f "$png" ] && [ "$png" -nt out/chair.blend ]; then echo "SKIP $v (up to date)"; continue; fi
  echo "START $v $(date +%H:%M:%S)"
  "$BLENDER" -b out/chair.blend -P scripts/render_chair.py -- "$v" "$PWD/$png" "$RES" "$SAMPLES" 2>&1 | grep -E "RENDERED|Traceback|Error" || echo "FAILED $v"
done
echo "ALL_DONE $(date +%H:%M:%S)"
