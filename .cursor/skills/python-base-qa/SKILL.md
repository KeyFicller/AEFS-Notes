---
name: python-base-qa
description: >-
  Use when adding or continuing a Python standard-library exercise under
  codes/python_base: writing qa.ipynb, reviewing answers, embedding 评阅 and
  参考答案, or generating card.png. Triggers include stdlib.md 的下一个模块、
  python_base、qa.ipynb、评阅、参考答案、模块卡片.
---

# python_base 模块练习

索引是 `codes/python_base/stdlib.md`。一次只处理用户点名的模块和步骤。出题时不要写答案。

## 目录

`{模块名}` 用表格第一列，原样作目录名（`urllib.request` 保留点号）。

```text
codes/python_base/{模块名}/qa.ipynb
codes/python_base/{模块名}/card.png          # 仅当用户要求出卡
codes/python_base/{模块名}/<题目目录>/       # 运行时产物，不进 git
```

需要读写外部文件时，工作空间就是 `{模块名}` 目录。路径相对 `ROOT`，不要写到仓库根，也不要依赖内核的当前目录。

`.gitignore` 已有 `codes/python_base/*/*/`（只忽略模块下的子目录）。`qa.ipynb` 和 `card.png` 留在模块根上，继续跟踪。模式缺失时补上，不要另写死 `q2`–`q7`。

## 做哪一步

| 用户要 | 做 | 不做 |
| --- | --- | --- |
| 出题 / 下一个模块 | 只写问题描述和前置代码 | 评阅、参考答案、卡片 |
| 审阅 | 评阅和参考答案嵌入作答格 | 只在对话里给答案；删掉或改写用户的作答 |
| 出卡 | 在模块目录生成 `card.png` | 写到 `notes/cards/` |

## 出题

笔记本中文。题量不固定，按这个模块有多少常用点、值不值得练来定。问题写清要做什么，少加实现禁令。

每题两格：Markdown 问题描述，代码格是前置代码加空的 `# 作答`。前置代码准备环境即可，不要把这题的写法示范出来。各题文件目录互相独立，放在 `ROOT` 下。

**不要为凑最后一题硬塞读写文件。** 只有模块本身就围绕路径/文件/序列化（如 `pathlib`、`os`、`json`、`csv`、`shutil`、`logging` 写日志文件）时，才出文件题；`random`、`math`、`hashlib`、`functools`、`itertools`、`typing`、`enum` 等用模块内的 API 收束即可（`hashlib` 可对内存中的 bytes 做摘要，不必为收束而写文件）。

开篇说明：先运行下一格得到 `ROOT`；只改 `# 作答`；先不要对答案。`ROOT` 用这段，把 `pathlib` 换成当前模块名：

```python
from pathlib import Path

def lab_root() -> Path:
    """qa.ipynb 所在目录。"""
    here = Path.cwd().resolve()
    for folder in [here, *here.parents]:
        if folder.name == "pathlib" and (folder / "qa.ipynb").is_file():
            return folder
        candidate = folder / "codes" / "python_base" / "pathlib"
        if (candidate / "qa.ipynb").is_file():
            return candidate
    return here

ROOT = lab_root()
ROOT
```

## 审阅

用户说审阅时，默认把评阅和参考答案嵌进笔记本。对话里只点出要看的题，不把全文再贴一遍。

评阅对准题目要做什么，不因为跑出了输出就算对。参考答案用该模块的惯用法，短，接在前置代码后面就能跑。

接在用户作答之后，不改原作答。两段都是注释，格式与 `codes/python_base/pathlib/qa.ipynb` 一致。标记不要改字，评阅和参考答案之间空一行：

```python
#评阅
# 对。用 / 拼接，name、stem、suffix、parent 都取对了。

#参考答案
# path = root / "src" / "app.py"
# print(path.name, path.stem, path.suffix, path.parent)
```

错了就在 `#评阅` 里写错在哪，参考答案仍然整段注释。再跑单元格不会执行参考答案。

## 出卡

只在用户要求时出。先读 [template-card.md](../aefs-lesson-memo/template-card.md)，版式按那份走。路径例外：文件落在 `codes/python_base/{模块名}/card.png`，不要写到 `notes/cards/`。

用 Cursor `GenerateImage`，`aspect_ratio` 为 `3:4`。按模板四层排，不要把写法平均铺成一排代码框：

- 身份：眉头是模块名，标题一句中文，Motto 一行。轻，别抢主视觉。
- 主视觉：1–2 个必须记住的写法，最大。代码按笔记本惯用法，1–3 行。
- 支撑：只在能澄清主视觉时放短标签。
- 边角：一个坑，小。

图上不要印「英雄点」或 `HERO`。`description` 里用「上区 / 主视觉 / 边角」，不要写会被照抄的 HERO。不要发明模块里没有的层。无 URL、无答案。生成后读图，文字错了就重画一次。
