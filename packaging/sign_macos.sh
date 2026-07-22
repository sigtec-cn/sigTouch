#!/bin/bash
# packaging/sign_macos.sh — 用稳定自签名证书深签 SigTouch.app
#
# 为什么需要:PyInstaller 默认 adhoc 签名,CDHash 每次重建都变;macOS TCC
# (辅助功能/输入监控/摄像头)按 CDHash 识别应用,重建后旧授权即失效(表现为
# "已勾选但检测不到"、输入监控面板条目对不上)。改用持久自签名证书后,
# designated requirement 变为按证书指纹锚定(certificate leaf = H"..."),
# 授权跨重建保持有效。
#
# 前置:证书已导入登录钥匙串(双击 packaging/codesign/sigtouch_dev.p12,密码见该目录)。
# 用法: packaging/sign_macos.sh [app路径]   默认 dist/SigTouch.app
set -euo pipefail

IDENTITY="${SIGTOUCH_SIGN_IDENTITY:-SigTouch Dev}"
APP="${1:-SigTouch.app}"

if [[ ! -d "$APP" ]]; then
    echo "错误: 找不到 app bundle: $APP" >&2
    exit 1
fi

if ! security find-certificate -c "$IDENTITY" >/dev/null 2>&1; then
    echo "错误: 钥匙串中找不到证书 '$IDENTITY'。" >&2
    echo "请先双击导入 packaging/codesign/sigtouch_dev.p12" >&2
    exit 1
fi

# 自底向上逐层签名:先所有内层二进制(框架/动态库/扩展/可执行件),再签 bundle 本体。
# 不用 codesign --deep:--deep 对 PyInstaller 的复杂内层结构常报 errSecInternalComponent。
sign_file() {
    codesign --force --sign "$IDENTITY" "$1" >/dev/null 2>&1 || true
}

echo "==> 签内层二进制"
# 先签嵌套最深的,逐层向外。覆盖 Frameworks 与 MacOS 下的 .dylib/.so/可执行件。
find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 2>/dev/null \
  | while IFS= read -r -d '' f; do sign_file "$f"; done

# 无扩展名的可执行件(如 python 解释器、辅助二进制)
find "$APP/Contents" -type f -perm +111 ! -name "*.dylib" ! -name "*.so" \
    ! -path "*/MacOS/*" -print0 2>/dev/null \
  | while IFS= read -r -d '' f; do
      # 跳过脚本/文本
      if file "$f" | grep -q "Mach-O"; then sign_file "$f"; fi
    done

echo "==> 签主可执行"
find "$APP/Contents/MacOS" -type f -perm +111 -print0 2>/dev/null \
  | while IFS= read -r -d '' f; do
      codesign --force --sign "$IDENTITY" "$f"
    done

echo "==> 签 bundle 本体"
codesign --force --sign "$IDENTITY" "$APP"

echo "==> 校验"
codesign --verify --deep --strict --verbose=1 "$APP"
echo "==> 签名身份:"
codesign -dvvv "$APP" 2>&1 | grep -iE "Authority|Identifier" | head -2
echo "完成: $APP"
