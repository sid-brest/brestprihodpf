#!/usr/bin/env bash
# Deploy prihodpfbrest.by: pull the repo and copy ONLY the files the site needs into public_html.
# Build tooling (scss/, schedule/, package.json, README) and source files never reach the web root.
set -euo pipefail

REPO="${REPO:-/home/prihodpf/repositories/brestprihodpf}"
WEBROOT="${WEBROOT:-/home/prihodpf/public_html}"

git -C "$REPO" reset --hard
git -C "$REPO" pull --ff-only

rsync -a --chmod=D755,F644 \
  --include='/index.html' \
  --include='/robots.txt' \
  --include='/sitemap.xml' \
  --include='/css/' --include='/css/vendor.min.css' --include='/css/style.min.css' \
  --include='/js/'  --include='/js/vendor.min.js'   --include='/js/custom.min.js' \
  --include='/img/' --include='/img/*.webp' --include='/img/*.jpg' --include='/img/*.png' --include='/img/*.ico' \
  --include='/fonts/' --include='/fonts/icomoon/' --include='/fonts/icomoon/*.woff2' \
  --include='/fonts/miama-nueva/' --include='/fonts/miama-nueva/*.woff2' --include='/fonts/miama-nueva/LICENSE.txt' \
  --exclude='*' \
  "$REPO/" "$WEBROOT/"

# One-off cleanup of files published by the old deploy script (safe to re-run).
rm -rf "$WEBROOT/schedule" "$WEBROOT/scss" "$WEBROOT/css/vendor" "$WEBROOT/css/default-skin" "$WEBROOT/js/vendor" \
       "$WEBROOT/fonts/icomoon demo" "$WEBROOT/gulpfile.js" "$WEBROOT/package.json" "$WEBROOT/README.txt" \
       "$WEBROOT/css/styles-merged.css" "$WEBROOT/css/styles-merged.css.map" "$WEBROOT/css/style.css" \
       "$WEBROOT/js/scripts.js" "$WEBROOT/js/scripts.min.js" "$WEBROOT/js/custom.js" "$WEBROOT/img/favicon.svg" \
       "$WEBROOT/fonts/icomoon/icomoon.eot" "$WEBROOT/fonts/icomoon/icomoon.svg" "$WEBROOT/fonts/icomoon/icomoon.ttf" "$WEBROOT/fonts/icomoon/icomoon.woff"
