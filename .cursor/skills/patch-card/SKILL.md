---
name: patch-card
description: >-
  按用户点名的修改项，局部改写已有 PNG 备忘卡 / card.png，其余画面不动。
  仅当用户显式调用本 skill（如 /patch-card、提到 patch-card）时使用；
  禁止因「卡片有错字 / 看起来不对」自动触发。
disable-model-invocation: true
---

# 局部改卡（patch-card）

只改用户列出的项。未点名的版式、文案、配色、构图一律保留。

## 何时用

- 用户显式调用本 skill，并给出目标卡路径 + 要改什么。
- 例：`/patch-card`、`用 patch-card`、`按 patch-card 改这张卡`。

## 何时不用

- 新出一张卡（走出卡 skill，如 `aefs-lesson-memo` / `python-base-qa`）。
- 用户只说「卡片有问题」但没显式点本 skill → 先问要不要用 patch-card，不要自行开改。
- 用户没给出目标文件且上下文也无法唯一确定路径 → 问一次。

## 输入

| 项 | 要求 |
|----|------|
| 目标卡 | 已有 PNG 的绝对或仓库相对路径（如 `codes/langchain/10_middleware/card.png`） |
| 修改清单 | 用户原话里的具体改动；缺则问一次，不要猜 |

把用户原话里的改动抄成编号清单，后续只允许动清单内条目。

## 流水线

1. 确认目标卡存在；不存在则停并报告。
2. `GetDynamicTools` → `cursor` / `GenerateImage`。
3. `CallDynamicTool` → `GenerateImage`：
   - `reference_image_paths` = **目标卡当前绝对路径**（必填）
   - `aspect_ratio` 与原卡一致；不确定时用 `"3:4"`
   - `filename` = 目标卡 basename（如 `card.png`）
   - `description` 模板见下
4. 从工具回执取产出 PNG 绝对路径；`cp` **覆盖**目标卡原路径。
5. `Read` 覆盖后的目标卡，只核对清单内条目是否改对。
6. 清单项仍错 → 至多再跑 **1** 次（同一参考图 = 刚覆盖的目标卡，description 只重申未修好的清单项）。仍错 → 交付当前文件并报告未修好项。
7. 回传：目标路径 + 已改条目；禁止 `![](...)`。

### description 模板

```text
RETRY — only apply the listed edits below. Keep EVERYTHING else identical
to the reference image (layout, colors, fonts, flowchart, stickers, footer,
title, motto, spacing, decorations). Exact visual clone except these edits.

Edits (and nothing else):
1. <用户改动 1，尽量用用户原词>
2. <用户改动 2>
...

Do not fix other typos. Do not redesign. Do not add or remove sections.
```

禁止在 description 里夹带清单外的「顺便修正」。

## 硬规则

- **最小改动**：用户没写的错字、构图、风格问题一律不碰。
- **同路径覆盖**：改的是原文件，不另存 `card-v2.png`，除非用户要新路径。
- **禁止** PIL/浏览器截图/外部 API/SVG 硬贴；只走 Cursor `GenerateImage`。
- **禁止** 借机重画整卡、换英雄点、补内容。
- 一次请求只改一张卡；多张则按用户指定顺序各跑一遍流水线。
