SigTouch Dev 自签名代码签名证书
================================
用途: 给 SigTouch.app 提供跨重建稳定的 TCC 身份(辅助功能/输入监控/摄像头授权
      不再因重建失效)。designated requirement 按证书指纹锚定而非每次变的 CDHash。

文件:
  sigtouch_dev.p12       私钥+证书(导入钥匙串用),密码: sigtouch
  sigtouch_dev_cert.pem  证书(供 codesign requirement / 分发核对)

一次性安装:
  双击 sigtouch_dev.p12 → 输入密码 sigtouch → 导入「登录」钥匙串。

之后 packaging/build_macos.sh 会自动用该证书签名。
正式发布请改用 Apple Developer ID 证书 + 公证(本自签名仅供本地/内部测试)。
