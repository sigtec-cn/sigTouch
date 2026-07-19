# SigTouch v1.3 设计文档:UI 视觉与交互刷新

日期:2026-07-19
状态:已确认
关联:v1 / v1.1 / v1.2 设计文档(同目录)

## 1. 目标与决策

**目标**:设置窗、权限引导窗、调试预览窗、托盘四个用户界面做到清新、美观、交互方便合理。

| 决策 | 结论 |
|---|---|
| 主题策略 | 固定清新浅色主题(自建 QSS,零新运行时依赖);深色模式留后续 |
| 设置保存交互 | **即时生效**:去掉 OK/Cancel/Apply,底部仅「恢复默认」「关闭」;重量级改动 500ms 防抖 |
| 第三方 UI 库 | 不引入(打包风险与风格不可控) |
| 应用图标 | 程序化生成(Pillow 仅 dev 依赖),icns/ico 资产入库 |

## 2. 主题系统(新增 `sigtouch/ui/theme.py`)

设计 token(模块常量,QSS 由 f-string 组装):

| Token | 值 | 用途 |
|---|---|---|
| `BG` | `#F7F9FA` | 窗口底色 |
| `CARD` | `#FFFFFF` | 卡片/输入底 |
| `BORDER` | `#E3E8EB` | 边框/分隔线 |
| `TEXT` | `#1F2933` | 主文字 |
| `TEXT_MUTED` | `#6B7680` | 说明文字 |
| `ACCENT` | `#14B8A6` | 主色(青绿) |
| `ACCENT_HOVER` | `#0D9488` | 主色 hover |
| `OK` | `#10B981` | 成功/已授权 |
| `WARN` | `#F59E0B` | 等待/许可中 |
| `DANGER` | `#EF4444` | 未授权/错误 |

- `apply_theme(app: QApplication) -> None`:设置全局 QSS——QDialog/QWidget 底色、QPushButton(默认描边样式 + `class="primary"` 实心青绿 + `class="danger"`)、QComboBox、QSpinBox/QDoubleSpinBox、QSlider(青绿滑轨)、QCheckBox、QListWidget(导航态选中左侧竖条高亮)、QLabel `class="muted"/"title"/"badge-ok"/"badge-danger"`;圆角:卡片 8px、控件 6px;统一 13px 字号(标题 15-17px 加粗)。
- 控件级 class 通过 `widget.setProperty("class", "...")` + QSS 属性选择器 `QPushButton[class="primary"]` 实现。
- `main()` 在 QApplication 创建后调用 `apply_theme(app)`;所有窗口自动继承。

## 3. 设置窗口重构(`sigtouch/ui/settings_dialog.py`)

### 3.1 布局

- 左侧 `QListWidget` 导航(固定宽 ~140px):📷 摄像头 / ✋ 交互 / 🎨 显示 / ⚙️ 通用;右侧 `QStackedWidget` 页面,导航切换页。
- 每页为滚动安全的卡片容器:页标题(加粗)+ 分组表单;设置项 = 控件 + 右侧当前值(滑杆类)+ 下一行灰色说明文字。
- 窗口固定尺寸约 660×480,居中。

### 3.2 控件升级

| 配置键 | 控件 | 说明文字 |
|---|---|---|
| interaction/box_margin | QSlider 5–30(%) + 数值 | 交互框边缘留白,越大越省手臂 |
| display/overlay_opacity | QSlider 10–100(%) + 数值 | 影子不透明度 |
| interaction/smooth_min_cutoff | QSlider 1–50(×0.1) + 数值 | 越低越平滑,越高越跟手 |
| 其余 | 维持 SpinBox/Combo/Check/颜色按钮 | 每项一句说明 |

### 3.3 即时生效

- `_fields` 注册表保留 `(widget, getter, setter)` 结构与 `field_widget()`;新增每控件变更信号统一接到 `_on_field_changed(key)`:
  - 立即 `cfg.set(key, getter())`;
  - key ∈ `_RESTART_KEYS`(camera/* 与 interaction/active_hand)→ 重置 500ms 单次 QTimer,超时后发 `vision_restart_needed` 信号;
  - 其余 key → 立即发 `settings_applied`(沿用既有信号名,语义变为"轻量应用")。
- 底部按钮:「恢复默认」(全部 key 写回 DEFAULTS、控件回读、随后按上述规则生效)与「关闭」(仅 hide)。
- `apply()` 方法保留为全量写回工具(恢复默认与测试用),不再有 Apply 按钮。

### 3.4 app 侧(`sigtouch/app.py`)

- `settings_applied` → `_apply_light_settings()`:重建 interaction 对象(machine/mapper/gate)、`overlay.apply_screen()`、`_setup_hotkey()`、autostart 同步、`release_all()` 前置(既有安全语义保留)——**不重启视觉线程**。
- `vision_restart_needed` → `_restart_vision()`(含轻量应用)。
- 现 `_on_settings_applied` 拆分为上述两个入口,行为总和与 v1.2 等价。

## 4. 权限引导窗卡片化(`sigtouch/ui/permission_wizard.py`)

- 顶部:标题「SigTouch 权限设置」(17px 加粗)+ 副标题(muted):"授权后无需重启,应用会自动激活"。
- 每项权限一张卡片(白底圆角 8px、1px 边框):左侧 emoji 图标(📷/🖱️/⌨️)+ 标题与说明;右上状态徽章 pill(绿底白字「✓ 已授权」/ 红底白字「✗ 未授权」);右下按钮组:主色「请求权限」(未授权时)+ 描边「打开系统设置」。
- 全就绪:顶部出现绿色成功横幅卡「✓ 全部权限已就绪,SigTouch 已自动激活」,2s 后自动关闭(逻辑不变)。
- **行为契约不变**:`checker/requester/opener` 注入、`refresh()`、`all_granted` 升沿一次、timer 生命周期(granted/hide 停,show 未就绪启)。
- 测试适配:`_status_labels[kind].text()` 断言由 "✓"/"✗" 改为 `startswith("✓")/startswith("✗")`(徽章文案带字)。

## 5. 调试预览窗与托盘

- 预览窗:深色画布(`#101418`)、零边距、固定初始 800×620、窗口标题「SigTouch 调试预览」保留;cv2 叠加信息保留(绿骨架/红锚点/黄文本在深底上对比度足够)。
- 托盘图标重绘(`sigtouch/ui/icons.py`):64px 抗锯齿——状态色圆底 + 白色简化手掌(圆掌 + 五指圆头短柱),四态色沿用(绿/灰/黄/红);`make_icon(color_hex)` 签名不变。
- 托盘菜单文案加 emoji 前缀:「⏸ 暂停」/「▶ 恢复」、「⚙️ 设置…」、「🔐 权限设置…」、「🎥 调试预览」、「⏻ 退出」;`_STATE_META` 第三元组值同步(暂停/恢复带图标)。

## 6. 应用图标

- `scripts/generate_icons.py`(依赖 Pillow,加入 dev extra):绘制 1024px 主图(青绿圆底 + 白色手掌图形,与托盘同族),导出:
  - macOS:iconset 各尺寸 → `iconutil` 合成 `assets/icon.icns`(脚本内调用,仅 darwin 可运行);
  - Windows:多尺寸 `assets/icon.ico`(Pillow 直接保存);
  - 两个资产**提交入库**(构建机不再需要 Pillow)。
- `packaging/sigtouch.spec`:`EXE(..., icon="../assets/icon.ico")`(win32 时)与 `BUNDLE(..., icon="../assets/icon.icns")`;非对应平台 PyInstaller 忽略/条件化处理。

## 7. 测试策略

- `theme.apply_theme`:offscreen 冒烟——应用后 `app.styleSheet()` 非空,且含 ACCENT 色值(QSS 语法错误会被 Qt 静默丢弃,故断言样式表原文注入即可 + 手动核验)。
- 设置即时生效:offscreen——改滑杆值 → `cfg.get` 立即变化;连续两次改 camera/index → `vision_restart_needed` 防抖后仅发一次(用 `QTimer` + `qapp.processEvents`/直接触发 timer timeout 测试);轻量键改动 → `settings_applied` 立即发;「恢复默认」把改过的键还原。
- 既有 settings roundtrip / wizard 测试:适配新结构(接口与语义保留,断言按 §4 调整)。
- app 双路径:harness 断言 `settings_applied` 不再重启 vision(stub 记录 stop 调用次数),`vision_restart_needed` 走 `_restart_vision`。
- 图标脚本:CI 不跑(资产入库);本地生成一次并人工目检。
- manual-qa 追加第 13 项:主题观感走查(设置窗导航/滑杆即时生效、权限卡片、托盘新图标与菜单、.app 图标显示)。

## 8. 明确不做(v1.3)

- 深色模式、动画/过渡效果。
- 第三方 UI 组件库。
- Linux 托盘图标平台特化、Windows 任务栏角标。
- 预览窗 Qt 原生绘制重构(保留 cv2 叠加)。
