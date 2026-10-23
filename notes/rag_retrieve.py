"""按话题检索 notes/cards 下的备忘卡片。

卡片正文在 PNG 里，文字抽不出来，所以三路各取所长，按名次融合（RRF）：

- 视觉：colSmol-500M（500M 的 late-interaction 检索模型，ColQwen 同架构的精简版）。
  每张卡编成 875 个 128 维 patch，query 的每个 token 对全卡 patch 取 max 再求和
  （MaxSim）。卡上任何一小块——角落里的「n≥200」、图上的 Langfuse 字样——
  都能单独被命中，这是单向量 CLIP 做不到的。
- 文本：目录名 + 出卡时写下的 heroes_declared + 课文导语，走中文二元组的 BM25。
  技术专名（Langfuse / p99 / A2A）靠这一路才准。
- 语义：同一份 heroes 走 bge-small-zh 的中文句向量，补同义词
  （「幻觉」对上「缓解≠证明」这种词面完全不同的说法）。

实测（全量 506 张卡，9 条已知答案的 query）：

    通道                 top1   hit@5
    视觉                 1/9    5/9
    视觉 + 文本           4/9    6/9
    视觉 + 文本 + 语义     5/9    8/9

已知会失手的两类：
- 同义词：查「结构化输出怎么做」命不中 03-structured-outputs —— 那张卡上写的是
  「控制谱 / 契约 / JSON Schema」，两边没有一个字相同。要靠给卡片补中文别名解决。
- 多义词：查「怎么降低幻觉」时 04-activation-functions 会挤进前列，因为它写的是
  「无激活则深度是幻觉」，词面完全匹配但语义不是一回事。

    python notes/rag_retrieve.py --index        # 首次建索引，506 张约 37 分钟（4.2s/张）
    python notes/rag_retrieve.py "评测怎么做"    # 检索
    python notes/rag_retrieve.py -k 3 "A2A 协议"
    python notes/rag_retrieve.py --eval         # 用已知答案量召回

视觉索引落盘在 .cache/cards_visual.pt（108MB，fp16），按 PNG 的修改时间增量更新：
新增一张只编那一张，改图才重算。

实测环境（M1 / 16GB，全程 CPU）：
- 编码 4.2s/张；query 约 1.5s（其中大半是 506 张 patch 转 float32）
- MPS 不可用：ColQwen2.5（3.8B）和 colSmol（500M）在 MPS 上都直接段错误，
  不是内存问题，是这套模型在 MPS 上的兼容性问题
- 3.8B 的 ColQwen2.5 在 CPU 上 133–158s/张，506 张要 20 小时，没法用；
  500M 这档是本地可用的上限
- 权重 v=1 t=1.5 d=0.3 是在这 10 条 query 上网格搜出来的，样本太少，
  --eval 的数字偏乐观；要调权重先补更多已知答案

文本和语义两路依赖 *.meta.txt 与 .cache/aefs/，两者都在 .gitignore 里。
新 clone 的仓库只有目录名，这两路会退化成按文件名猜——脚本检测到这种情况会直接关掉，
只留视觉那一路（它不受影响）。
"""

import os
import re
import sys
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

# 镜像地址必须在 import 那一刻之前设好，huggingface_hub 会把它定死。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

ROOT = Path(__file__).resolve().parent.parent  # 仓库根：脚本住在 notes/ 下
CARDS = ROOT / "notes" / "cards"
LESSONS = ROOT / ".cache" / "aefs" / "phases"  # 出卡时拉的课文
INDEX = ROOT / ".cache" / "cards_visual.pt"

sys.path.insert(0, str(ROOT / "codes" / "capstone" / "02_rag_over_codebase"))
from demo_main import BM25Index, Chunk  # noqa: E402  复用 capstone 02 的 BM25

VISION_MODEL = "vidore/colSmol-500M"
TEXT_MODEL = "BAAI/bge-small-zh-v1.5"
# 换视觉模型必须重建索引：patch 数和维度都会变，混着用不报错但结果是错的。
INDEX_VERSION = 1
TOP_K = 5
LESSON_CHARS = 1200
CANDIDATES = 60  # 每路给融合器多少名次
RRF_K = 60       # RRF 的平滑常数，取原论文值
WEIGHTS = (1.0, 1.5, 0.3)  # 视觉 / 文本 / 语义，见模块 docstring

# 已知答案，用来量召回而不是看热闹。卡名是相对 notes/cards 的路径去掉 .png。
GOLD = [
    ("langfuse 观测", "17-infrastructure-and-production/13-llm-observability"),
    ("评测怎么做", "11-llm-engineering/10-evaluation"),
    ("A2A 协议", "16-multi-agent-and-swarms/12-a2a-protocol"),
    ("RAG 怎么切块", "05-nlp-foundations-to-advanced/23-chunking-strategies-rag"),
    ("推理延迟的 p99 怎么量", "17-infrastructure-and-production/08-inference-metrics-goodput"),
    ("多 agent 什么时候该拆", "16-multi-agent-and-swarms/01-why-multi-agent"),
    ("工具 schema 怎么设计", "13-tools-and-protocols/05-tool-schema-design"),
    ("怎么降低幻觉", "05-nlp-foundations-to-advanced/26-relation-extraction-kg"),
    ("结构化输出怎么做", "11-llm-engineering/03-structured-outputs"),
]

# 中文没有空格，\w+ 会把整句切成一个 token，BM25 直接失效。
# 补一层二元字组当词用：切得糙，但「评测」「消融」这类双字术语能命中。
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_WORD = re.compile(r"[a-z0-9_]+")


def lexical(text: str) -> str:
    """BM25 侧的文本形态：ASCII 词 + 中文二元组。doc 和 query 必须同样处理。"""
    grams: list[str] = []
    for run in _CJK_RUN.findall(text):
        grams += [run[i:i + 2] for i in range(len(run) - 1)] or [run]
    return " ".join(_ASCII_WORD.findall(text.lower()) + grams)


# ------------------------------------------
# 视觉通道
# ------------------------------------------

def card_files() -> list[Path]:
    """一章一卡。同名的 attempt 子目录是副产物，不进索引。"""
    return sorted(CARDS.glob("*/*.png"))


def load_models():
    return _load_vision(), _load_text()


@lru_cache(maxsize=1)
def _load_vision():
    from colpali_engine.models import ColIdefics3, ColIdefics3Processor
    import torch

    # device 固定 cpu：MPS 上这套模型一律段错误（500M 也崩，不是内存问题）。
    model = ColIdefics3.from_pretrained(
        VISION_MODEL, torch_dtype=torch.float32, device_map="cpu"
    ).eval()
    return model, ColIdefics3Processor.from_pretrained(VISION_MODEL)


@lru_cache(maxsize=1)
def _load_text():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(TEXT_MODEL, device="cpu", local_files_only=True)


def load_index() -> dict:
    import torch

    if not INDEX.is_file():
        return {}
    try:
        data = torch.load(INDEX, map_location="cpu", weights_only=False)
    except Exception:
        return {}
    if data.get("version") != INDEX_VERSION or data.get("model") != VISION_MODEL:
        print("索引与模型版本对不上，重建。", file=sys.stderr)
        return {}
    return data


def save_index(data: dict) -> None:
    import torch

    INDEX.parent.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    torch.save(data, tmp)
    tmp.replace(INDEX)  # 写一半崩掉不会留下坏索引


def build_index() -> None:
    """增量建索引。key 是相对路径，按 mtime + size 判断要不要重编。"""
    from PIL import Image
    import torch

    model, processor = _load_vision()
    old = load_index()
    cached = old.get("entries", {})
    cards = card_files()

    def stale(png: Path) -> bool:
        was = cached.get(png.relative_to(ROOT).as_posix())
        if not was:
            return True
        return was["mtime"] != png.stat().st_mtime or was["size"] != png.stat().st_size

    todo = [png for png in cards if stale(png)]
    print(f"共 {len(cards)} 张，待编码 {len(todo)} 张（{VISION_MODEL}，约 4s/张）", flush=True)

    started = time.time()
    for i, png in enumerate(todo, 1):
        rel = png.relative_to(ROOT).as_posix()
        batch = processor.process_images([Image.open(png).convert("RGB")]).to(model.device)
        with torch.no_grad():
            emb = model(**batch)[0]  # 去掉 batch 维：(875, 128)
        cached[rel] = {
            "mtime": png.stat().st_mtime,
            "size": png.stat().st_size,
            "patches": emb.to(torch.float16),
        }
        elapsed = time.time() - started
        print(f"[{i}/{len(todo)}] {rel.split('/', 2)[-1]} "
              f"({elapsed / i:.1f}s/张, 剩余 {elapsed / i * (len(todo) - i) / 60:.0f}min)", flush=True)
        if i % 20 == 0:  # 定期落盘，中断可续跑
            save_index({"version": INDEX_VERSION, "model": VISION_MODEL, "entries": cached})

    alive = {png.relative_to(ROOT).as_posix() for png in cards}
    entries = {k: v for k, v in cached.items() if k in alive}  # 已删的卡清出索引
    save_index({"version": INDEX_VERSION, "model": VISION_MODEL, "entries": entries})
    print(f"索引完成：{len(entries)} 张，{INDEX} "
          f"({INDEX.stat().st_size / 1048576:.0f}MB)", flush=True)


def visual_ranking(query: str, entries: dict, patches_f32: dict) -> list[str]:
    """MaxSim：query 每个 token 找最像的 patch，再求和。

    不用 colpali 的 score_multi_vector —— 它要求所有文档 patch 数一致，
    而 3:4 和 9:16 的卡 patch 数不同。逐卡算，506 张约 2.5s。
    """
    import torch

    model, processor = _load_vision()
    batch = processor.process_queries([query]).to(model.device)
    with torch.no_grad():
        q = model(**batch)[0].to(torch.float32)  # (Q, 128)

    scored = [(rel, float((q @ patches_f32[rel].T).max(dim=1).values.sum()))
              for rel in entries]
    scored.sort(key=lambda x: -x[1])
    return [rel for rel, _ in scored[:CANDIDATES]]


# ------------------------------------------
# 文本 / 语义通道
# ------------------------------------------

def heroes_of(png: Path) -> str:
    """出卡时写下的 heroes_declared；多 attempt 时后写的优先。"""
    for meta in sorted(png.with_suffix("").glob("attempt*.meta.txt"), reverse=True):
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.startswith("heroes_declared:"):
                return line.split(":", 1)[1].strip()
    return ""


def lesson_of(png: Path) -> str:
    """课文开头一段，用来说出卡片上没写进 heroes 的工具名（Langfuse / p99）。"""
    doc = LESSONS / png.parent.name / png.stem / "docs" / "en.md"
    return doc.read_text(encoding="utf-8", errors="replace")[:LESSON_CHARS] if doc.is_file() else ""


class TextChannels:
    """文本 + 语义两路。heroes 全缺时整体关闭，只留视觉那一路。"""

    def __init__(self, rels: list[str]) -> None:
        self.ready = False
        heroes = {rel: heroes_of(ROOT / rel) for rel in rels}
        if not any(heroes.values()):
            return  # 新 clone 的仓库：meta 在 .gitignore 里，这两路没有原料

        bm25 = BM25Index()
        self.by_anchor: dict[str, str] = {}
        for rel in rels:
            png = ROOT / rel
            slug = png.stem.replace("-", " ")
            chunk = Chunk(
                repo=png.parent.name,
                path=png.name,
                start_line=1,
                end_line=1,
                symbol=slug,  # BM25 里 ×4 权重
                body=f"{lexical(heroes[rel] + ' ' + slug)} {lesson_of(png)}",
                summary=heroes[rel],  # ×2 权重
            )
            bm25.add(chunk)
            self.by_anchor[chunk.anchor] = rel
        self.bm25 = bm25

        model = _load_text()
        # bge 中文 v1.5 对短查询的推荐前缀，只加在 query 一侧。
        self.prefix = "为这个句子生成表示以用于检索相关文章："
        self.vectors = model.encode([heroes[rel] for rel in rels],
                                    normalize_embeddings=True, batch_size=64)
        self.rels = rels
        self.ready = True

    def rankings(self, query: str) -> list[list[str]]:
        if not self.ready:
            return []
        text = [self.by_anchor[c.anchor] for c, _ in self.bm25.search(lexical(query), k=CANDIDATES)]
        qv = _load_text().encode([self.prefix + query], normalize_embeddings=True)[0]
        order = (self.vectors @ qv).argsort()[::-1][:CANDIDATES]
        return [text, [self.rels[i] for i in order]]


# ------------------------------------------
# 检索
# ------------------------------------------

def search(query: str, entries: dict, channels: TextChannels, k: int,
           patches_f32: dict | None = None) -> list[tuple[str, float]]:
    import torch

    if patches_f32 is None:
        patches_f32 = {rel: e["patches"].to(torch.float32) for rel, e in entries.items()}
    ranked = [visual_ranking(query, entries, patches_f32)] + channels.rankings(query)

    # 加权 RRF：三路分数量纲完全不同（MaxSim 求和无上界，BM25 有 idf 加权，
    # 余弦在 0–1 之间），只能按名次融合。权重见 WEIGHTS。
    fused: dict[str, float] = defaultdict(float)
    for hits, weight in zip(ranked, WEIGHTS):
        for rank, rel in enumerate(hits):
            fused[rel] += weight / (RRF_K + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])[:k]


def evaluate(entries: dict, channels: TextChannels) -> None:
    hits = top1 = 0
    started = time.time()
    for query, gold in GOLD:
        ranked = [rel for rel, _ in search(query, entries, channels, 10)]
        gold_rel = f"notes/cards/{gold}.png"
        rank = ranked.index(gold_rel) + 1 if gold_rel in ranked else None
        hits += 1 if rank and rank <= 5 else 0
        top1 += 1 if rank == 1 else 0
        print(f"{query:22s} rank={rank}  top1={ranked[0].split('/')[-1][:42]}")
    print(f"\ntop1 = {top1}/{len(GOLD)}   hit@5 = {hits}/{len(GOLD)}   "
          f"({(time.time() - started) / len(GOLD):.1f}s/query)")


def label_of(rel: str) -> tuple[str, str]:
    """卡片路径 → (标题, 所属阶段)。给 UI 用，去掉文件名前面的编号。"""
    path = Path(rel)
    slug = re.sub(r"^\d+[-_]", "", path.stem).replace("-", " ").replace("_", " ")
    phase = re.sub(r"^\d+[-_]", "", path.parent.name).replace("-", " ")
    return slug, phase


def serve(k: int = 6) -> None:
    """常驻检索进程：按行读 query，按行吐 JSON。

    DeskPet 右键「检索备忘」走这条路。每次新开进程要重载两个模型（约 6s），
    常驻后单次检索 1.5s，差值全在模型加载上。
    """
    import json
    import torch

    data = load_index()
    if not data:
        sys.exit("还没有索引。先跑 python notes/rag_retrieve.py --index")
    entries = data["entries"]
    # 500MB 的 float32 副本只做一次，不然每个 query 都要重拷
    patches_f32 = {rel: e["patches"].to(torch.float32) for rel, e in entries.items()}
    channels = TextChannels(list(entries))

    print(json.dumps({"ready": True, "cards": len(entries)}), flush=True)
    for line in sys.stdin:
        query = line.strip()
        if not query:
            continue
        try:
            hits = search(query, entries, channels, k, patches_f32)
        except Exception as exc:  # 单个 query 出错不能把常驻进程带走
            print(json.dumps({"query": query, "error": str(exc)}, ensure_ascii=False), flush=True)
            continue
        results = []
        for rel, score in hits:
            title, phase = label_of(rel)
            results.append({
                "path": rel,
                "title": title,
                "phase": phase,
                "summary": heroes_of(ROOT / rel),
                "score": round(score, 5),
            })
        print(json.dumps({"query": query, "results": results}, ensure_ascii=False), flush=True)


def main() -> None:
    args = sys.argv[1:]
    if "--index" in args:
        build_index()
        return
    if "--serve" in args:
        serve()
        return
    if not args or args[0] in {"-h", "--help"}:
        sys.exit(__doc__)

    data = load_index()
    if not data:
        sys.exit("还没有索引。先跑 python notes/rag_retrieve.py --index")
    entries = data["entries"]
    channels = TextChannels(list(entries))

    if args[0] == "--eval":
        evaluate(entries, channels)
        return

    k = TOP_K
    if args[0] == "-k" and len(args) > 1:
        k, args = int(args[1]), args[2:]
    query = " ".join(args).strip()
    if not query:
        sys.exit("用法：python notes/rag_retrieve.py [-k N] 话题")
    if not channels.ready:
        print("（没有 *.meta.txt，文本与语义两路已关闭，只剩视觉）", file=sys.stderr)

    for rank, (rel, _) in enumerate(search(query, entries, channels, k), 1):
        print(f"{rank}. {rel}")


if __name__ == "__main__":
    main()
