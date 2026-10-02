"""生产版多页文档 QA：真页文件 → Document → 多向量 patch → MaxSim → LCEL 作答。

demo_main.py 用假 hash 向量和写死 CORPUS 把 late interaction 跑通；这里把能交给
框架的交给框架，交不出去的说清为什么。

和 demo_main.py 的对应：
- CORPUS 三元组硬编码     -> pages/ 下的 .md 页文件，扫盘装成 Document
- Page.content_tokens     -> Document.page_content + metadata(doc_id, page_num)
- hash_embed / EMB_DIM=16 -> HuggingFaceEmbeddings + all-MiniLM-L6-v2（384 维，真语义）
- doc_prune / max_sim     -> 继续用 demo_main 的。langchain 没有 MaxSim，
                             VectorStore 是一文档一向量，接不上 late interaction
- Index.retrieve 打印 top-k -> 同样 MaxSim 召回，再走 LCEL 让模型带着 citation 回答
- 检索的 bug（for t in query 按字符切）-> 这里 tokenize 后再 embed，按词

诚实说明（和 01「PyTorch 不在这条链路」、02「DeepSeek 没有 embeddings」同类）：

1. Document 只是页容器。本课的英雄点是「一页很多向量 + MaxSim」，不是「装进 Document」。
   InMemoryVectorStore / similarity_search 做的是 bi-encoder 单向量召回，接上去等于
   把 demo 的机制整段换掉。所以 Document 负责身份（doc_id / page_num / 正文），
   多向量索引和 MaxSim 仍自己管。
2. 真 ColPali 是页图 → ViT patch。这里没有 byaldi / 页图编码器，用「词 = patch」
   的文本近似保住 late interaction 骨架；换 ColPali 只换 embed_page 那一层。
3. DeepSeek 没有 embeddings 接口，向量只能本地算。语料是英文页，选已经在缓存里的
   all-MiniLM-L6-v2（~90MB），不用再下。normalize_embeddings=True，余弦退化成点积，
   跟 demo 的 max_sim_score 前提一致。
4. DocPruner 仍按向量 L1 丢低信号 patch。真系统会按注意力或 PQ 量化来压存储；
   这里只保留「召回前先裁」这个决策点，好对照 demo 的 ablation。
5. 页文件写死在 pages/：主题对齐 demo 的 CORPUS（10-K、ViDoRe、手写实验、图表），
   方便同一组问题验召回。要换语料，往 pages/<doc_id>/pNNN.md 丢文件即可。

用法：
    1. 顶部 QUESTION 写问题（留空会跑一组自带问题）
    2. python prod_main.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# huggingface_hub 在 import 时就把 ENDPOINT 定死；国内直连会超时，镜像要抢在前面。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_CAPSTONE = Path(__file__).resolve().parents[1]
if str(_CAPSTONE) not in sys.path:
    sys.path.insert(0, str(_CAPSTONE))

from common import load_local_env
from demo_main import doc_prune, max_sim_score, tokenize
from huggingface_hub import try_to_load_from_cache

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings

# ===== 运行前改这里。留空则跑 DEFAULT_QUESTIONS。 =====
QUESTION = "what was the 2024 operating margin change for EMEA"

KEEP_FRACTION = 0.5
TOP_K = 3
DEFAULT_MODEL = "deepseek-v4-flash"
# 英文页；缓存里已有。换模型不用手动清索引——每次启动重 embed，页数很少。
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
PAGES_ROOT = Path(__file__).resolve().parent / "pages"

_PAGE_FILE_RE = re.compile(r"^p(\d+)\.md$", re.IGNORECASE)

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你在做多页文档问答。只根据给出的页面回答，不要补充页面之外的知识。\n"
     "每条结论后面用 [doc_id p.页码] 标注来源，doc_id 和页码原样抄。\n"
     "页面里找不到就直说找不到，不要猜。"),
    ("human", "页面：\n\n{context}\n\n问题：{question}"),
])

DEFAULT_QUESTIONS = [
    "what was the 2024 operating margin change for EMEA",
    "late interaction retrieval vs OCR",
    "handwritten experimental figures with error bars",
    "bar chart comparing segment margins",
]


# ------------------------------------------
# 扫盘 → Document
# ------------------------------------------

def load_pages(root: Path) -> list[Document]:
    """pages/<doc_id>/pNNN.md → Document。

    metadata 就是 MaxSim 命中之后回写 citation 的原料；page_content 是要切成
    patch 的正文。Document 到这里为止，后面不再进 VectorStore。
    """
    if not root.is_dir():
        raise FileNotFoundError(f"语料目录不存在：{root}")

    docs: list[Document] = []
    for path in sorted(root.rglob("*.md")):
        match = _PAGE_FILE_RE.match(path.name)
        if match is None:
            continue
        doc_id = path.parent.name
        page_num = int(match.group(1))
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        docs.append(Document(
            page_content=text,
            metadata={"doc_id": doc_id, "page_num": page_num, "path": path.as_posix()},
        ))
    return docs


def page_label(doc: Document) -> str:
    return f"{doc.metadata['doc_id']} p.{doc.metadata['page_num']}"


# ------------------------------------------
# 多向量索引（不进 VectorStore）
# ------------------------------------------

def model_is_cached() -> bool:
    return isinstance(try_to_load_from_cache(EMBED_MODEL, "config.json"), str)


def make_embedder() -> HuggingFaceEmbeddings:
    """本地句向量模型。词级 patch 也走同一条 embed_documents。

    device 固定 cpu：页数少，CPU 秒级；normalize 后点积 = 余弦，demo 的 MaxSim
    不用改。缓存命中就离线，避免每次 HEAD 镜像。
    """
    model_kwargs: dict[str, Any] = {"device": "cpu"}
    if model_is_cached():
        model_kwargs["local_files_only"] = True
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs=model_kwargs,
        encode_kwargs={"normalize_embeddings": True},
    )


def embed_tokens(embedder: Embeddings, tokens: list[str]) -> list[list[float]]:
    if not tokens:
        return []
    return embedder.embed_documents(tokens)


def patches_for(doc: Document, embedder: Embeddings, prune: bool) -> list[list[float]]:
    tokens = tokenize(doc.page_content)
    vectors = embed_tokens(embedder, tokens)
    if prune and vectors:
        return doc_prune(vectors, keep_fraction=KEEP_FRACTION)
    return vectors


class MaxSimIndex:
    """页 → 多向量。retrieve 走 demo 的 max_sim_score，不经 VectorStore。"""

    def __init__(self) -> None:
        self.pages: list[Document] = []
        self.patches: list[list[list[float]]] = []

    def add(self, doc: Document, patch_vectors: list[list[float]]) -> None:
        if not patch_vectors:
            return
        self.pages.append(doc)
        self.patches.append(patch_vectors)

    def retrieve(self, query: str, embedder: Embeddings, k: int = TOP_K) -> list[tuple[Document, float]]:
        q_tokens = tokenize(query)
        q_vecs = embed_tokens(embedder, q_tokens)
        if not q_vecs:
            return []
        scored = [
            (page, max_sim_score(q_vecs, patches))
            for page, patches in zip(self.pages, self.patches)
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


def build_index(docs: list[Document], embedder: Embeddings, prune: bool) -> MaxSimIndex:
    index = MaxSimIndex()
    for doc in docs:
        index.add(doc, patches_for(doc, embedder, prune=prune))
    return index


# ------------------------------------------
# 作答
# ------------------------------------------

class UsagePrinter(BaseCallbackHandler):
    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.calls += 1
        for batch in response.generations:
            for generation in batch:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                self.tokens += int((usage or {}).get("total_tokens") or 0)


def format_context(hits: list[tuple[Document, float]]) -> str:
    return "\n\n".join(
        f"[{page_label(doc)}]\n{doc.page_content}" for doc, _ in hits
    )


def build_chain(
    index: MaxSimIndex,
    embedder: Embeddings,
    usage: UsagePrinter,
) -> Runnable[str, str]:
    """MaxSim 召回 → 拼 context → 模型。检索是 RunnableLambda：框架没有 MaxSim retriever。"""

    def retrieve(query: str) -> list[tuple[Document, float]]:
        return index.retrieve(query, embedder, k=TOP_K)

    return (
        {
            "context": RunnableLambda(retrieve) | format_context,
            "question": RunnablePassthrough(),
        }
        | ANSWER_PROMPT
        | init_chat_model(f"deepseek:{DEFAULT_MODEL}", temperature=0)
        | StrOutputParser()
    ).with_config({"callbacks": [usage]})


def ask(query: str, chain: Runnable[str, str], index: MaxSimIndex, embedder: Embeddings, usage: UsagePrinter) -> str:
    hits = index.retrieve(query, embedder, k=TOP_K)
    print(f"\nQ: {query}")
    for doc, score in hits:
        print(f"   score={score:+.3f}  {page_label(doc)}")
    answer = chain.invoke(query)
    print("-" * 72)
    print(f"model calls={usage.calls}  tokens={usage.tokens}")
    print("-" * 72)
    print(answer)
    return answer


def ablation(docs: list[Document], embedder: Embeddings) -> None:
    """对照 demo 的 pruning off vs on。看 top-3 页身份叠不叠得上。"""
    full = build_index(docs, embedder, prune=False)
    pruned = build_index(docs, embedder, prune=True)
    query = "chart comparing segment margins"
    full_top = [page_label(doc) for doc, _ in full.retrieve(query, embedder, 3)]
    prn_top = [page_label(doc) for doc, _ in pruned.retrieve(query, embedder, 3)]
    print("\n=== ablation: pruning off vs on ===")
    print(f"  full    top-3 : {full_top}")
    print(f"  pruned  top-3 : {prn_top}")
    print(f"  overlap       : {len(set(full_top) & set(prn_top))}/3")


# ------------------------------------------
# 入口
# ------------------------------------------

def main() -> None:
    load_local_env(Path(__file__).resolve().parent)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("缺少 DEEPSEEK_API_KEY。可写在环境变量或 deskpet/local.env。")

    docs = load_pages(PAGES_ROOT)
    if not docs:
        sys.exit(f"{PAGES_ROOT} 下没有 pages/<doc_id>/pNNN.md。")

    embedder = make_embedder()
    index = build_index(docs, embedder, prune=True)
    patch_total = sum(len(p) for p in index.patches)
    print(
        f"语料 {len(docs)} 页 → 索引 {len(index.pages)} 页，"
        f"prune={KEEP_FRACTION:.0%} 后共 {patch_total} 个 patch"
        f"（{EMBED_MODEL}）"
    )

    usage = UsagePrinter()
    chain = build_chain(index, embedder, usage)
    questions = [QUESTION.strip()] if QUESTION.strip() else DEFAULT_QUESTIONS
    for query in questions:
        # 每问重置计数，避免多问时累加看起来像「这一问烧了好多 token」。
        usage.calls = 0
        usage.tokens = 0
        ask(query, chain, index, embedder, usage)

    ablation(docs, embedder)


if __name__ == "__main__":
    main()
