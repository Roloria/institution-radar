#!/bin/zsh
# 构建 site/ 并发布到 GitHub Pages (gh-pages 分支)
set -e
cd "$(dirname "$0")/.."
.venv/bin/python scripts/build_static.py

TMP=$(mktemp -d)
TAG=$(date '+%Y%m%d-%H%M%S')
git -C "$TMP" init -q -b gh-pages
git -C "$TMP" config user.name "institution-radar-bot"
git -C "$TMP" config user.email "Roloria@users.noreply.github.com"
cp -R site/* "$TMP/"
git -C "$TMP" add -A
git -C "$TMP" commit -qm "publish snapshot $TAG"
git -C "$TMP" remote add origin https://github.com/Roloria/institution-radar.git
git -C "$TMP" push -q --force origin gh-pages
rm -rf "$TMP"
echo "[deploy] gh-pages 已更新 ($TAG) -> https://roloria.github.io/institution-radar/"
