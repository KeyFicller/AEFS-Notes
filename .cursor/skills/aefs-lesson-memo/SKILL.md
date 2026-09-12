---
name: aefs-lesson-memo
description: >-
  在用户明确要求为 AEFS（AI Engineering from Scratch）某一课生成中文备忘卡 /
  章节卡片 / lesson memo / PNG 卡片时使用。触发意图须含「出卡 / 备忘卡 / PNG」类动词；
  仅讨论 AEFS、只读 phases/... 课文、不要图时不要使用。
---

# AEFS 课文备忘卡

**定位：** 整个学习项目指向 **AI 工程**（训练 / 推理 / LLM / 生成式模型 / 数据与评测管线），不是纯数学习题册。备忘卡萃取的知识点必须与 AI 内容**高关联**。

默认一课 → **一张 PNG**。英雄点占画面；不交付 markdown。  
仅当课文主体是**大量并列子项**时，再加一张 `xx-` 旁卡（见「枚举课」）。

评测：[evaluator.md](evaluator.md)（**≥ 85**；**初稿 + 至多 1 次重画**）。

## 何时用 / 不用

- **用**：用户要为本课出备忘卡 / 章节卡片 / lesson memo / PNG。
- **不用**：只要 markdown 笔记、多课批量、非 AEFS、只要评分不要出图、纯讨论课文。

## 启动

1. 确认课文 id（`phases/<phaseDir>/<lessonDir>` 或可解析 URL）；缺则问一次。
2. 走工作流。回传路径 + motto + score；依赖客户端自动展示工具图，禁止 `![](...)`。

## 课文源（唯一）

| 项 | 规则 |
|----|------|
| Upstream | `https://github.com/rohitg00/ai-engineering-from-scratch`（权威；**禁止换 fork**，除非用户指定） |
| 正文 | `phases/<phaseDir>/<lessonDir>/docs/en.md` |
| URL | 只认 `?path=phases/...` 或路径中的 `phases/...`；失败 → 问一次 |
| 本地 | 优先 workspace / `.cache/aefs/` 已有该树 |
| 冲突 | living 正文 vs 纸书 → 以 living `en.md` 为准 |

### 拉取顺序（优先镜像）

直连 GitHub 常超时/HTTP2 失败 → **先镜像、后官方、最后 clone**。落盘到 `.cache/aefs/phases/<phaseDir>/<lessonDir>/`。

```text
1. 本地已有该课 en.md → 直接用
2. 镜像 raw（按序试，首个 HTTP 200 且正文非空即停）:
   a. https://cdn.jsdelivr.net/gh/rohitg00/ai-engineering-from-scratch@main/<path>
   b. https://raw.gitmirror.com/rohitg00/ai-engineering-from-scratch/main/<path>
   c. https://ghproxy.net/https://raw.githubusercontent.com/rohitg00/ai-engineering-from-scratch/main/<path>
3. 官方 raw:
   https://raw.githubusercontent.com/rohitg00/ai-engineering-from-scratch/main/<path>
4. 仍失败 → 同一 upstream 浅克隆/sparse 到 .cache/aefs/（可用 GIT_HTTP_LOW_SPEED 等；勿换 fork）
```

`<path>` 例：`phases/01-math-foundations/10-dimensionality-reduction/docs/en.md`。课内 `code/` 同序拉取（文件名可从 en.md 代码引用或目录 listing 推断）。curl 建议 `--connect-timeout 10 --max-time 30`。

路径派生（禁止扁平名 `notes/cards/*--*.png`）：

```text
输入 phases/<phaseDir>/<lessonDir>/...
phaseDir / lessonDir 原样用作目录名与文件名主干（已含 NN-slug）
canonical      = notes/cards/<phaseDir>/<lessonDir>.png          # 主产物
byproducts_dir = notes/cards/<phaseDir>/<lessonDir>/             # 与主产物同级的子文件夹
attemptN       = notes/cards/<phaseDir>/<lessonDir>/attemptN.png
metaN          = notes/cards/<phaseDir>/<lessonDir>/attemptN.meta.txt
GenerateImage.filename = <lessonDir>.png   # 仅 basename
副产物（attempt / meta）只进 byproducts_dir；勿与 canonical 平铺同目录

# 枚举课旁卡（仅触发「枚举课」时）
xx_slug         = xx-<topic-slug>            # 主题短名，非 lessonDir；如 xx-statistics-metrics
xx_canonical    = notes/cards/<phaseDir>/<xx_slug>.png
xx_byproducts   = notes/cards/<phaseDir>/<xx_slug>/
GenerateImage.filename = <xx_slug>.png       # 仅 basename
```

## 工作流

```
- [ ] 1. 解析课文路径（上表）
- [ ] 2. 按「拉取顺序」拉 en.md + 扫课内 code/（镜像优先）
- [ ] 3. 扫 Further Reading（核对用，不强制上卡）
- [ ] 4. 判定是否「枚举课」→ 章节英雄点；若是则另拟旁卡网格清单
- [ ] 5. 读 [methods.md](methods.md)（适配，勿硬套）
- [ ] 6. 生成–评测循环（每张卡：初稿 + 至多 1 次重画）
- [ ] 7. 更新 notes/progress.md（枚举课写两行）
```

交付物仅 PNG。

### 出图流水线（唯一，禁止另寻工具）

**只许**用 Cursor 内置 `GenerateImage`（`cursor` → `GenerateImage`）。  
禁止：Python/PIL、浏览器截图、外部 API、其他 MCP 画图、用 markdown/HTML 冒充卡片。

调用前：

1. `GetDynamicTools` namespace=`cursor` toolName=`GenerateImage`（看清 schema）
2. `CallDynamicTool` namespace=`cursor` toolName=`GenerateImage`（cursor 命名空间**勿**加 `mcpDetails`）
3. 以工具回执中的绝对路径为准；**禁止猜测**默认目录

| 参数 | 规则 |
|------|------|
| `description` | 必填。按 [template-card.md](template-card.md) + 英雄点写清版式/文案/风格；RETRY 时把 ≤5 条修正指令放在最前 |
| `filename` | 章节卡仅 `<lessonDir>.png`；旁卡仅 `<xx_slug>.png`（**勿带目录**） |
| `aspect_ratio` | 默认 `"3:4"`；需纵向用 `"9:16"`；本 skill 只用这两档 |
| `reference_image_paths` | 仅 RETRY：上一次 attempt PNG 的**绝对路径** |

落盘（每次生成后立刻做）：

```text
1. CallDynamicTool → GenerateImage
2. 从工具回执读取产出 PNG 的绝对路径；无路径则停止并报告（禁止改用其他出图方式）
3. mkdir -p notes/cards/<phaseDir>/<lessonDir>/
4. mv/cp 到副产物目录：
   notes/cards/<phaseDir>/<lessonDir>/attempt<N>.png
5. Read 该 attempt PNG → 按 evaluator 打分
6. 若优于已保存最佳（先 hard_gates=pass，再比 total）：
   cp 覆盖 canonical：notes/cards/<phaseDir>/<lessonDir>.png
7. 写 sidecar（同副产物目录）：
   notes/cards/<phaseDir>/<lessonDir>/attempt<N>.meta.txt
```

### 生成–评测

打分与硬门槛、最佳选取以 [evaluator.md](evaluator.md) 为准；此处只管次数与流水线。

```text
attempt = 1
best = none
loop:
  按「出图流水线」生成到 <lessonDir>/attempt<N>.png 并打分
  按 evaluator 规则更新 best → 必要时刷新 canonical
  ACCEPT → 确保 canonical = 本次；交付；break
  RETRY 且 attempt < 2 → attempt++；≤5 条指令 + reference_image_paths=[本次 attempt 绝对路径]；重走流水线
  否则 EXHAUST → 交付 canonical（best）；报告最佳 score 与失败项；break
```

### 英雄点

动笔前点名 **1–2** 个必须记住的点（偶可为紧绑双子）；写入评分卡 `heroes_declared`。

- 候选优先**课文正文**（主题 / Learning Objectives / 双高 H2 / Key Terms / 课内代码 punchline）
- H2、FR 都是主题补充，**不强制**上卡、不照抄标题
- 分流（三维，缺一则缩小或丢）：
  1. **AI 关联度**：能否直接接到模型、训练、推理、评测、数据或 LLM/生成式管线（课文里的 Connection to ML / Use It / 生产例子优先）
  2. **本课主题关联度**：是否本课核心机制，而非邻课或冷门附录
  3. **工程落地重要性**：这周能否写进真实脚本 / 调试决策
- **双高或三高上卡**；纯数学好奇、历史典故、与 AI 弱相关的推导细节 → 缩小或丢
- 同一机制有「教科书定义」与「AI 用法」时：**主视觉用 AI 用法锚定**（如马尔可夫→扩散/LLM；卷积定理→CNN/FFT 卷积；拉普拉斯→GNN/谱聚类）
- 口号不得挤掉可落地机制；英雄点最大，支撑缩小或删

### 枚举课（章节卡 + xx- 旁卡）

**默认只出章节卡。** 不要把每课都拆成两张。

**判定「枚举课」**（同时满足才拆）：

- 课文主体是**大量并列、同级**的子项目录（每种一个公式/算法/适用场景），不是一条主机制再带几个例子
- 子项大约 **≥ 6**（度量、距离、采样法、损失族等）；或用户明确要求「网格枚举 / 单独 xx- 卡」
- 例：统计指标、采样方式。反例：信息论（一条恒等式）、SVD（几何三拍）、数值稳定性（先减 max）→ **只出章节卡**

用户点名把某一块拆出去（如 einsum 从张量课拆出）→ 可出 `xx-`，但不因此把该课当成枚举课、不必再堆第二张目录。

**两张怎么分：**

| 卡 | 写什么 | 不写什么 |
|----|--------|----------|
| 章节卡 `notes/cards/<phaseDir>/<lessonDir>.png` | 决策/机制要点（何时用、易踩坑、1–2 英雄点） | 全文清单、等权格子墙 |
| 旁卡 `notes/cards/<phaseDir>/xx-<topic-slug>.png` | 编号网格枚举全部可见子项 | 长段决策文、自测 |

旁卡版式对齐已有网格卡（如 `14-norms-and-distances`）：①–N 虚线格，每格 **名 + 公式/一步算法 + 微图 + 短用途**；底条只放 1–2 条总规则。章节卡脚注可写「清单见旁卡 xx-…」，勿把网格再抄一遍。

每张卡独立走「生成–评测」（各最多 2 次）。`progress.md` 两行：`phases/.../<lessonDir>` 与 `phases/.../xx-<topic-slug>`。回传两张都报路径 + score。

### 生产代码 punchline（学习者偏好）

学习者同步在练 **Python / PyTorch / LangChain / LangGraph**。课文或课内 `code/` 若出现**关联度极高**的生产惯用法，**应上卡**（可读短片段，非整文件）：

- 例：`device = torch.device("cuda" if torch.cuda.is_available() else "cpu")`
- 优先：设备选择、venv/uv 激活检查、可复现 seed、常见 API 骨架（chain / graph 节点）、错误回退
- **供应商示例默认 OpenAI 路线**（`OPENAI_API_KEY` / `openai` SDK / chat.completions）；课文若写 Anthropic/Google，上卡时改写为等价 OpenAI 模式，勿并列多厂商
- 判定：与本课英雄点同题，且本周就能抄进真实脚本 → 上；仅为演示噪音 → 不上
- 版式：贴英雄点旁或作次主视觉；字号够手机读；声明了代码英雄点则图上必须可读（见 evaluator 硬门槛）

### 文案库存

**默认只保留标题 + 英雄主视觉。** 下列槽位仅当直接服务英雄点时启用，默认不填：

Motto / 今日能做啥 · 概念便签 · 数字钩 / Build↔Use / **生产代码 punchline** / 坑

短标签。拥挤砍非英雄点。无答案、无自测、无 FR 堆、无配套 md。双高生产代码与概念英雄冲突时：**保留概念主视觉，代码缩成一句 punchline 贴纸**，勿等权两栏。

**禁止自测**：图上不要自测栏、自测问句、灯泡测验。缺席，不改成「想一想」。

### 产出

- 方法 [methods.md](methods.md) · 版式 [template-card.md](template-card.md) · 风格 [examples.md](examples.md)
- 最终路径：`notes/cards/<phaseDir>/<lessonDir>.png`；枚举课另加 `notes/cards/<phaseDir>/xx-<topic-slug>.png`
- 出图只走上方流水线

### progress.md

```text
若无 notes/progress.md：mkdir -p notes 并创建，写入表头
| date | lesson path | card file | status |
同 lesson path 已有行则覆盖，否则追加
card file：相对仓库根的 canonical 路径
status：done score=N attempt=K  |  exhaust score=N attempt=K
ACCEPT 与 EXHAUST 都必须更新；中途崩溃不写 done
```

## 视觉

要：层次清、手绘公众号感、手机可读、生产 punchline 该上就上。  
不要：长文墙、答案、自测、英文分区墙、FR/QA 堆、等权分区、图标沙拉。

## 回传

- ACCEPT：canonical 路径 + motto + score（枚举课两张都报）
- RETRY：继续，不写长文
- EXHAUST：canonical 路径 + 最佳 score + 失败项
