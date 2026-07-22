#!/bin/bash
# packaging/build_macos.sh — macOS 一键构建:PyInstaller 打包 + 稳定证书签名
# 在仓库根目录执行: packaging/build_macos.sh
# 产物: packaging/dist/SigTouch.app(已用稳定自签名证书深签,TCC 授权跨重建有效)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYI="${PYI:-$ROOT/.venv/bin/pyinstaller}"

cd "$ROOT/packaging"
echo "==> PyInstaller 打包"
"$PYI" sigtouch.spec --noconfirm

echo "==> 稳定证书签名"
./sign_macos.sh dist/SigTouch.app

echo ""
echo "构建完成: $ROOT/packaging/dist/SigTouch.app"
