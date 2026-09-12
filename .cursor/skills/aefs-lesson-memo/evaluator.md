# PNG 评测器

每次生成后 Read **attempt PNG** → 打分 → ACCEPT / RETRY / EXHAUST。

## 常量

| 项 | 值 |
|----|-----|
| 接受 | **总分 ≥ 85 / 100** |
| 次数 | **初稿 + 至多 1 次重画**（attempt 1…2） |
| 耗尽 | 留硬门槛通过中最高分；若无则最高分；报告失败项 |
| 落盘 | 副产物进 `notes/cards/<phaseDir>/<lessonDir>/attemptN.png`（及 `.meta.txt`）；优于 best 时再 cp 到同级 canonical（见 SKILL） |

硬门槛失败 ⇒ 该次作废（即使总分 ≥ 85）；作废稿不得成为 best（除非尚无任何 hard_gates=pass 的稿，耗尽时才退而求其次用最高分）。

## 量规（100）

各维整数 0…权重，求和。

| ID | 维度 | 权重 | 看什么 |
|----|------|------|--------|
| H1 | 英雄点落地 | 35 | 声明的英雄点最大、可点名；关键机制非脚注 |
| H2 | 层次 | 17 | 主次清；无图标沙拉、无 H2 标题墙 |
| H3 | 可读 | 15 | 手机可读；代码/公式非糊团 |
| H4 | 契约 | 15 | 中文为主；无答案/无自测/长文墙；手绘感；无 FR 堆 |
| H5 | 准确 | 18 | 对齐课文；无概念错；英雄点与 AI 工程钩子一致（非纯偏门数学） |

### 硬门槛（任一失败 ⇒ Reject）

1. 英雄点缺失或仅脚注暗示
2. 图上有答案或自测栏/自测问句
3. 主内容是英文分区墙/长文
4. 声明了生产代码英雄点，但代码缺失或不可读
5. 高 AI 关联×高落地要点缺失/脚注，而偏门、口号或与 AI 弱相关的纯数学细节霸屏

不因缺 FR 徽章、未把 FR 专名做成英雄点而 Reject。不查配套 md。

## 评分卡（每次必出）

```text
attempt N/2
heroes_declared: …
H1: xx/35 — …
H2: xx/17 — …
H3: xx/15 — …
H4: xx/15 — …
H5: xx/18 — …
hard_gates: pass | fail (reason)
total: xx/100
verdict: ACCEPT | RETRY | EXHAUST
redraw_directives:   # 仅 RETRY；≤5 条；只修失败
- …
```

- ACCEPT：门槛过且 ≥ 85
- RETRY：未过且 attempt < 2
- EXHAUST：未过且 attempt = 2

## 重画

必须重走 SKILL「出图流水线」：仅 `cursor` → `GenerateImage`。  
RETRY：≤5 条指令置 `description` 顶；`reference_image_paths` = **本次失败 attempt PNG** 的绝对路径；勿中途改英雄点（除非定义不足，重述一次）。

ACCEPT / EXHAUST：交付 **canonical**（best）+ progress（`done|exhaust score=… attempt=…`）。无配套 md。
