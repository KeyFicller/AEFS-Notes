# DeskPet 划词浮标解释（Easydict 风格）

日期：2026-09-21  
状态：已批准设计，待实现

## 目标

学习时选中专有名词 / 简写后，在指针旁出现小浮标；**点击浮标**后用现有 DeepSeek 解释链路弹出气泡，无需再拖到桌宠上。

## 已确认决策

| 项 | 选择 |
|---|---|
| 交互 | 划词 → 出浮标 → **点击**才解释（不做悬停触发） |
| 选区来源 | Accessibility API（v1）；不做 Force ⌘C |
| 旧路径 | **保留**拖文本到桌宠 |
| 权限 | 需 macOS「辅助功能」；未授权时不出浮标，菜单可引导授权 |

## 非目标（v1）

- 悬停自动解释
- 模拟 ⌘C / 抢剪贴板
- 改提示词、气泡样式、模型配置
- 跨用户多显示器的复杂选区几何（够用即可：指针附近放置）

## 架构

```
[全局 mouseUp]
    → SelectionWatcher（AX 读选区）
    → 有有效文本？ → SelectionChipPanel 显示在指针旁
    → 用户点击 chip
        → 隐藏 chip
        → AppDelegate.explain(term)（复用 ExplainClient + SpeechBubble）
```

### 新组件

1. **`SelectionWatcher`**
   - 全局 `leftMouseUp`（及必要时 `otherMouseUp` 忽略）
   - 防抖：短延迟后再读 AX，避免拖选过程中误触发
   - 调用 AX 获取 focused 元素的选中字符串
   - 过滤：trim 后为空、纯空白、长度 > 200 → 忽略
   - 若点击发生在 DeskPet 自身窗口上 → 忽略（避免点浮标/气泡时递归）

2. **`SelectionChipPanel`**
   - 无边框、悬浮、`NSPanel`，约 28×28
   - 内容：简单「?» 或桌宠小图（实现时用系统符号 / 文字即可）
   - 显示在 `NSEvent.mouseLocation` 右上方，夹入当前屏 `visibleFrame`
   - 点击 → `onTap(selectedText)`
   - 自动隐藏：再划新词替换、点击屏幕其他处（可选全局 mouseDown）、超时（如 5s）

3. **接线（`AppDelegate`）**
   - 启动时若有辅助功能权限则 `SelectionWatcher.start()`
   - `onTap` → 现有 `explainDroppedText` / 等价入口（不触发出卡）
   - 右键菜单：「授予辅助功能权限…」→ `AXIsProcessTrustedWithOptions` 提示或打开系统设置 URL

## 权限 UX

- 启动不强制弹窗（避免烦人）；第一次划词失败且未授权时，可打一次系统 prompt，或仅菜单引导
- v1 推荐：菜单项打开设置；stderr 打一行提示即可

## 配置

v1 可用代码常量；可选后续进 `local.env`：

- `EXPLAIN_CHIP_MAX_CHARS=200`
- `EXPLAIN_CHIP_TIMEOUT_SECONDS=5`

非必须，实现时用常量即可。

## 成功标准

1. 在 Text / Preview / 笔记类 App 中划选短词，浮标出现在指针附近
2. 点击浮标 → 桌宠旁出现解释气泡（Markdown 富文本照旧）
3. 无辅助功能权限时：不出浮标，桌宠拖放解释仍可用
4. 点击浮标不会弹出学习卡片

## 风险

- 部分 Electron / 游戏窗口 AX 选区为空 → v1 接受；文档可注明
- 全局事件监控与浮标面板层级需仔细处理，避免抢焦点导致选区丢失（点击前应已缓存选中文本）
