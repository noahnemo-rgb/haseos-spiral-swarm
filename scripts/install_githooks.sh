#!/bin/sh
# D23 — HITL only. Point this clone at tracked githooks/.
# Cursor must not run this. core.hooksPath stays local to the clone.
set -eu
repo=$(git rev-parse --show-toplevel)
git -C "$repo" config core.hooksPath githooks
git -C "$repo" config --get core.hooksPath
