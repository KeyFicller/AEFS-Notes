"""生产版 Code RAG：真扫盘 → 切块 → 向量库落盘 → 两路召回 → LCEL 检索链。

demo_main.py 每一层都是手搓的；这里把能交给框架的交给框架，交不出去的说清为什么。

和 demo_main.py 的对应：
- SAMPLE_CORPUS 的 6 条硬编码 -> scan_chunks()：真扫目录 + RecursiveCharacterTextSplitter
- fake_embed / _token_hash     -> HuggingFaceEmbeddings + BAAI/bge-small-zh-v1.5，真语义
- DenseIndex（list + 暴力余弦）-> InMemoryVectorStore，dump/load 落盘
- BM25Index                    -> 继续用 demo_main 的。langchain 1.x 没有 BM25，
                                  装 rank_bm25 才有 BM25Retriever，本项目不装
- rrf / rerank                 -> 继续用 demo_main 的。框架里没有对应物
- answer() 组装的 dict          -> LCEL：RunnableParallel | prompt | model | StrOutputParser
- main() 逐阶段打印             -> 回调统一收口 + 最终答案（正文里带 citation）

诚实说明，跟 01 里「PyTorch 不在这条链路里」是同一类：

1. 向量是真模型算的，但只能在本地算：DeepSeek 没有 embeddings 接口
   （POST /v1/embeddings 返回 404，/v1/models 里全是 chat 模型），
   所以机器上唯一那个 key 没法提供向量。torch 本来就在 venv 里，
   加 sentence-transformers 的代价只是几个纯 Python 包，不用下框架本体。
   换真向量前后的实测（12 个「X 怎么用」查询，看 top1 是否落在对的模块）：
       假向量 256 维    dense 1/12   bm25 9/12   hybrid  9/12
       bge-small-zh     dense 11/12  bm25 9/12   hybrid 11/12
   假向量那一路基本是在抛硬币，混检也会被它拖住不加分——这就是它必须换掉的原因。
2. 选 bge-small-zh-v1.5：语料是中文技术笔记，中文语义是这系列的主场；95MB、512 维，
   CPU 上给 141 个 chunk 编码是秒级。要多语言换 paraphrase-multilingual-MiniLM-L12-v2，
   要长文本换 bge-m3（2.2GB）——不用手动清索引，指纹会触发重建，见 load_or_build_store。
3. 国内直连 huggingface.co 不通，靠 HF_ENDPOINT 指到 hf-mirror.com 才下得下来。
   这个兜底只在环境变量没设过时生效，你自己设了就以你为准。
   嫌慢可以改从 ModelScope 取（实测快 11 倍），但要多一个下载步骤。
4. 模型的 max_seq_length 是 512 token，CHUNK_SIZE 却是 800 字符：纯中文的长 chunk
   尾部会被静默截断，那段文字对向量没有贡献。要根治就把 CHUNK_SIZE 降到 480 左右，
   代价是 chunk 数变多。
5. Chunk.summary 在这里是空串。demo 的 summary 是手写的，真语料没有对应物，
   于是 BM25 的 summary×2 和 rerank 的 summary_overlap 都落空——这正是真实系统
   要先跑一遍 LLM 生成摘要的原因。想恢复权重，给 .py 取 docstring、给 ipynb 取首个
   markdown cell，就是最小改法。
6. .ipynb 的行号是「提取出的 cell 源码」的行号，不是 .ipynb 这个 JSON 文件的行号。
   要精确指向原文件得改读原始行号，这里刻意不做。

用法（没有命令行参数，要改的都写在文件顶上）：
    1. 填上 QUESTION（首次运行会下 ~95MB 模型，之后走缓存）
    2. python prod_main.py

语料写死在 CORPUS_ROOT：python_stdlibs 下只索引 .ipynb。
索引和语料或模型对不上会自动重建；想强制重建，删掉 .index 目录即可。
"""

import json
import os
import re
import sys
from bisect import bisect_right
from collections.abc import Iterable
from hashlib import blake2b
from operator import itemgetter
from pathlib import Path
from typing import Any

# 这一行必须在任何第三方 import 之前。huggingface_hub 在 import 那一刻就把 ENDPOINT
# 定死，之后再改环境变量完全不生效（实测：import 完再 setdefault，它用的仍是
# huggingface.co）。国内直连 huggingface.co 是超时的，所以镜像兜底得抢在它前面。
# setdefault 而不是直接赋值：你自己设了 HF_ENDPOINT 就以你为准。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# common.py 和 demo_main.py 都在上一级（codes/capstone/），脚本直接跑时要自己补路径。
_CAPSTONE = Path(__file__).resolve().parents[1]
if str(_CAPSTONE) not in sys.path:
    sys.path.insert(0, str(_CAPSTONE))

from common import load_local_env
from demo_main import BM25Index, Chunk, rerank, rrf
from huggingface_hub import try_to_load_from_cache

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    Runnable,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ===== 运行前改这里：填上要问的问题。留空直接跑会提示补上。 =====
QUESTION = "collections的第四题讲了什么"

# 只索引 .ipynb（写死）。要放开到 .py / .md，往这个集合里加后缀即可。
# .png / .db / .csv / .log 这些既不是检索目标，也会把索引撑大。
SOURCE_SUFFIXES = {".ipynb"}

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# 换成真向量了：本地跑的中文 embedding 模型。选型理由见模块 docstring 第 1、2 条。
# 换模型不用手动清索引：指纹里有这条，会自动重建（见 load_or_build_store）。
EMBED_MODEL = "BAAI/bge-small-zh-v1.5"

# 两路各召回多少、融合后重排留几条。跟 demo 同量级：这个语料 140 来个 chunk，
# 召回 10 条已经是 7% 的语料，再大就没意义了。
CANDIDATES = 10
TOP_K = 5

DEFAULT_MODEL = "deepseek-v4-flash"
INDEX_DIRNAME = ".index"

# 语料写死在这里。锚在仓库根上，而不是当前目录，免得换个终端跑就找不到
# （索引本来就锚在文件位置，语料也一起锚住才一致）。
CORPUS_ROOT = Path(__file__).resolve().parents[3] / "codes" / "python_stdlibs"

# 从源码里认一个名字：.py 取 def / class，.md 和 ipynb 取标题。
# demo 的 symbol 是手填的，这里只能猜；猜不到就空串，BM25 里 symbol 那 4 倍权重
# 和 rerank 的 symbol_overlap 就各自落空，不会算错。
_SYMBOL_RE = re.compile(r"^(?:def|class)\s+(\w+)|^#{1,3}\s+(.+)", re.MULTILINE)

ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你在一个代码知识库里做检索问答。只根据给出的片段回答，不要补充片段之外的知识。\n"
     "每条结论后面用 [片段路径:起始行-结束行] 的形式标注来源，路径原样抄，不要改写。\n"
     "片段里找不到答案就直接说找不到，不要猜。"),
    ("human", "片段：\n\n{context}\n\n问题：{question}"),
])


# ------------------------------------------
# 扫盘与切块
# ------------------------------------------

def read_source(path: Path) -> str:
    """读一个源文件成纯文本。.ipynb 只取 cell 源码，丢掉 JSON 外壳、输出和图片。

    注意行号：这里返回的是拼出来的文本，它第 10 行不等于 .ipynb 文件的第 10 行。
    """
    if path.suffix == ".ipynb":
        notebook = json.loads(path.read_text(encoding="utf-8"))
        cells = (
            "".join(cell.get("source", []))
            for cell in notebook.get("cells", [])
            if cell.get("cell_type") in {"code", "markdown"}
        )
        return "\n".join(cells)
    return path.read_text(encoding="utf-8", errors="replace")


def file_symbols(text: str) -> list[tuple[int, str]]:
    """扫出文件里所有 def / class / 标题，返回 [(行号, 名字)]，按行号升序。"""
    found: list[tuple[int, str]] = []
    for match in _SYMBOL_RE.finditer(text):
        name = (match.group(1) or match.group(2) or "").strip()
        if name:
            found.append((text.count("\n", 0, match.start()) + 1, name))
    return found


def enclosing_symbol(symbols: list[tuple[int, str]], line: int) -> str:
    """chunk 起点之前最近的那个符号，才是它该署的名。

    不能就地在这个 chunk 的正文里搜：chunk 是从半句话上切开的，搜到的往往是
    下半段才开始的标题（实测出过 `symbol='对。type=int...'` 这种），署错名比不署名更糟。
    bisect 的 key= 是 3.10+ 的用法，按行号在 (行号, 名字) 表里二分。
    """
    index = bisect_right(symbols, line, key=itemgetter(0)) - 1
    return symbols[index][1] if index >= 0 else ""


# 各模块下的 q1..q7 是 qa.ipynb 运行时写下的答题目录（.gitignore 里也忽略了它们），
# 里面是 print(1)、`def greet()` 这类临时脚本，进了索引只会稀释召回。
# 名字规律就是 q + 数字，没有别的信号可用。
_QUESTION_DIR_RE = re.compile(r"q\d+\Z")


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        if any(_QUESTION_DIR_RE.fullmatch(part) for part in rel.parts):
            continue
        yield path


def scan_chunks(root: Path) -> list[Chunk]:
    """把目录切成 demo_main.Chunk，让 BM25 / rrf / rerank 能直接吃。

    分块交给 RecursiveCharacterTextSplitter（比 demo 的空行切法讲道理），
    行号靠 add_start_index 给的字符偏移反算。chunk_size 按字符算，中文会被切在
    分词中间，搜中文长句时准头会掉——要修，先换按 token 计数的分块器。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )

    chunks: list[Chunk] = []
    for path in iter_source_files(root):
        text = read_source(path)
        if not text.strip():
            continue
        rel = path.relative_to(root).as_posix()
        symbols = file_symbols(text)
        for piece in splitter.create_documents([text]):
            start_index = int(piece.metadata["start_index"])
            # start_index 是字符偏移，换成行号：数它前面有几个换行。
            # 末尾行号按 chunk 自己的行数推，重叠的部分允许相邻 chunk 头尾相接。
            start_line = text.count("\n", 0, start_index) + 1
            end_line = start_line + piece.page_content.count("\n")
            chunks.append(Chunk(
                repo=root.name,
                path=rel,
                start_line=start_line,
                end_line=end_line,
                symbol=enclosing_symbol(symbols, start_line),
                body=piece.page_content,
                summary="",  # 见模块 docstring 第 5 条
            ))
    return chunks


# ------------------------------------------
# 向量库
# ------------------------------------------

def to_document(chunk: Chunk) -> Document:
    """Chunk -> Document。metadata 就是 anchor 的原料，收索引和引用都用它。"""
    return Document(
        page_content=chunk.body,
        metadata={
            "anchor": chunk.anchor,
            "repo": chunk.repo,
            "path": chunk.path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol": chunk.symbol,
        },
    )


def model_is_cached() -> bool:
    """模型是否已经在 HF 缓存里。

    try_to_load_from_cache 命中给路径（str），没命中给 None。
    别想着用 HF_HUB_OFFLINE 环境变量代替：huggingface_hub 在 import 的时候就把那个
    常量定死了，运行到这儿再设已经晚了。
    """
    return isinstance(try_to_load_from_cache(EMBED_MODEL, "config.json"), str)


def make_embedder() -> HuggingFaceEmbeddings:
    """本地跑的中文 embedding 模型。

    device 固定 cpu：torch 报了 mps 不可用，而且 141 个 chunk 在 CPU 上本来就是秒级，
    为它绕 Metal 不划算。normalize_embeddings=True 让向量是单位长度，
    余弦相似度退化成点积，跟 demo_main 里 cosine_similarity 的前提一致。

    缓存命中就强制离线：huggingface_hub 每次加载都会发 HEAD 去核对缓存是否过期，
    而这个镜像建连要十几秒（实测联网 9.9s vs 离线 2.2s），每次跑都白等。
    首次仍要联网下那 95MB，所以只在命中时才切 local_files_only。
    """
    model_kwargs: dict[str, Any] = {"device": "cpu"}
    if model_is_cached():
        model_kwargs["local_files_only"] = True

    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs=model_kwargs,
        encode_kwargs={"normalize_embeddings": True},
    )


def build_store(
    chunks: list[Chunk],
    index_file: Path,
    embedder: Embeddings,
) -> InMemoryVectorStore:
    store = InMemoryVectorStore(embedding=embedder)
    store.add_documents([to_document(chunk) for chunk in chunks])
    index_file.parent.mkdir(parents=True, exist_ok=True)
    store.dump(str(index_file))
    return store


def load_or_build_store(
    chunks: list[Chunk],
    root: Path,
    index_dir: Path,
    embedder: Embeddings,
    rebuild: bool,
) -> InMemoryVectorStore:
    """有索引就读，没有或对不上就重建。

    为什么落盘：真系统里 embedding 要花钱、要等，重建一次就想哭。141 个 chunk 在
    CPU 上重编码要好几秒，落盘省掉的就是这几秒，也顺手把管线练完整。

    meta.json 不是为了缓存，是为了别读错索引。指纹里两样东西都不能少：
    - anchors 摘要：dense 那一路拿到 Document 之后要靠 anchor 换回 Chunk，
      行号一变就换不回来。不拦的话，那个 KeyError 会出现在检索最深处，
      看不出是索引过期。只改正文、行号没变的情况会放行——那时换得回来。
    - embed_model：换了模型，向量维度可能不同、语义完全不同，读旧索引等于
      拿别人的向量问自己的问题。跨模型不报错但结果错，是这里最危险的一种。
    """
    index_file = index_dir / "store.json"
    meta_file = index_dir / "meta.json"
    anchors = "\n".join(chunk.anchor for chunk in chunks).encode("utf-8")
    fingerprint = {
        "root": str(root.resolve()),
        "chunks": len(chunks),
        "anchors": blake2b(anchors, digest_size=16).hexdigest(),
        "embed_model": EMBED_MODEL,
    }

    if not rebuild and index_file.is_file() and meta_file.is_file():
        if json.loads(meta_file.read_text(encoding="utf-8")) == fingerprint:
            return InMemoryVectorStore.load(str(index_file), embedding=embedder)
        print("索引与语料对不上，重建。")

    store = build_store(chunks, index_file, embedder)
    meta_file.write_text(json.dumps(fingerprint, ensure_ascii=False), encoding="utf-8")
    return store


# ------------------------------------------
# 召回
# ------------------------------------------

def dense_hits(
    store: InMemoryVectorStore,
    by_anchor: dict[str, Chunk],
    query: str,
    k: int,
) -> list[tuple[Chunk, float]]:
    """向量库那一路。

    similarity_search_with_score 给的是相似度（越大越像），跟 BM25 和 demo 的余弦
    同向，所以能直接当 rerank 的 prior。换成返回距离的库（越小越好）要先取负，
    否则重排会优先挑最不相关的。
    """
    hits = store.similarity_search_with_score(query, k=k)
    return [(by_anchor[doc.metadata["anchor"]], score) for doc, score in hits]


def format_context(hits: list[tuple[Chunk, float]]) -> str:
    """把片段拼成 prompt 里的 context。anchor 摆在正文前面，模型抄 citation 时有得可抄。"""
    return "\n\n".join(f"[{chunk.anchor}]\n{chunk.body}" for chunk, _ in hits)


# ------------------------------------------
# 链路
# ------------------------------------------

class UsagePrinter(BaseCallbackHandler):
    """01 里的 HookBus 在这里收成回调：框架负责调用时机，我们只旁路记一笔。"""

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


def build_chain(
    store: InMemoryVectorStore,
    bm25: BM25Index,
    by_anchor: dict[str, Chunk],
    usage: UsagePrinter,
) -> Runnable[str, str]:
    """两路召回 -> RRF -> 重排 -> 拼 context -> 交给模型。

    retrieval 这一段是 RunnableLambda 而不是框架的 retriever：框架的 VectorStoreRetriever
    只走向量那一路，混合检索得自己拼。包成 Runnable 才能挂进 LCEL 管道。
    """
    retriever = RunnableLambda(lambda query: retrieve(query, store, bm25, by_anchor))

    return (
        RunnableParallel(context=retriever | format_context, question=RunnablePassthrough())
        | ANSWER_PROMPT
        | init_chat_model(f"deepseek:{DEFAULT_MODEL}", temperature=0)
        | StrOutputParser()
    ).with_config({"callbacks": [usage]})


def retrieve(
    query: str,
    store: InMemoryVectorStore,
    bm25: BM25Index,
    by_anchor: dict[str, Chunk],
) -> list[tuple[Chunk, float]]:
    """跟 demo 的 answer() 同构，只是 dense 那一路换成了向量库。"""
    dense = dense_hits(store, by_anchor, query, CANDIDATES)
    sparse = bm25.search(query, k=CANDIDATES)
    return rerank(query, rrf(dense, sparse), top_k=TOP_K)


def ask(query: str, chain: Runnable[str, str], usage: UsagePrinter) -> str:
    answer = chain.invoke(query)
    print("-" * 80)
    print(f"model calls={usage.calls}  tokens={usage.tokens}")
    print("-" * 80)
    print(answer)
    return answer


# ------------------------------------------
# 入口
# ------------------------------------------

def main() -> None:
    if not QUESTION.strip():
        sys.exit("请先在 prod_main.py 顶部的 QUESTION 里写上要问的问题。")

    root = CORPUS_ROOT
    if not root.is_dir():
        sys.exit(f"语料目录不存在：{root}")

    # ChatDeepSeek 在构造时就校验密钥，所以这一步必须在建模型之前。
    load_local_env(Path(__file__).resolve().parent)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("缺少 DEEPSEEK_API_KEY。可写在环境变量或 deskpet/local.env。")

    chunks = scan_chunks(root)
    if not chunks:
        sys.exit(f"{root} 下没有可索引的文件（只认 {'、'.join(sorted(SOURCE_SUFFIXES))}）。")

    embedder = make_embedder()
    store = load_or_build_store(
        # rebuild 固定 False：留空就按指纹判断。要强制重建就删掉 .index 目录。
        chunks, root, Path(__file__).resolve().parent / INDEX_DIRNAME, embedder, False
    )
    # 用 anchor 把向量库返回的 Document 换回 Chunk，BM25 / rrf / rerank 全程共用同一批对象。
    by_anchor = {chunk.anchor: chunk for chunk in chunks}

    bm25 = BM25Index()
    for chunk in chunks:
        bm25.add(chunk)

    print(f"语料 {len(chunks)} 个 chunk，来自 {root}")
    usage = UsagePrinter()
    ask(QUESTION, build_chain(store, bm25, by_anchor, usage), usage)


if __name__ == "__main__":
    main()
