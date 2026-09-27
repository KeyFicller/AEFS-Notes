"""Code RAG：dense + BM25 两路召回，RRF 融合，再重排。

混合检索的最小骨架：
1. Chunk：可被引用的代码片段（repo / path / 行号，用来生成 citation）
2. DenseIndex：假向量 + 余弦相似度
3. BM25Index：词频 + 逆文档频率
4. rrf：只看排名，把两路结果合成一个序
5. rerank：用 query 和 symbol / summary 的词面重叠做二次打分

搜「重构：」可以跳到每一处改动。注释写的是「为什么这样改」和「以后怎么接」，
不是复述代码在做什么。
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import blake2b
from operator import itemgetter
from typing import TypedDict

# ----------------------------
# Chunk shape
# ----------------------------


@dataclass
class Chunk:
    repo: str
    path: str
    start_line: int
    end_line: int
    symbol: str
    body: str
    summary: str

    @property
    def anchor(self) -> str:
        return f"{self.repo}/{self.path}:{self.start_line}-{self.end_line}"


# 硬编码的假语料，代替「扫一遍仓库再切片」。换成真扫描就是：walk 文件 →
# 按语法树或空行切 chunk → 填上面这几个字段。
SAMPLE_CORPUS = [
    Chunk("uploader", "services/retry.go", 122, 148, "AbortMultipartOnFail",
          "if ctx.Err() != nil { return abort() }; decrement bucket budget; retry with backoff",
          "aborts an in-flight S3 multipart upload and decrements the per-bucket retry budget"),
    Chunk("uploader", "config/budgets.yaml", 34, 51, "bucket_budget",
          "per_bucket_budget: 64; backoff_ms: [100, 500, 2500]; abort_threshold: 3",
          "declares the retry budget and exponential backoff schedule per S3 bucket"),
    Chunk("client", "libs/s3client/multipart.ts", 44, 61, "abortUpload",
          "await s3.abortMultipartUpload({Bucket, Key, UploadId}); metrics.inc('s3.abort')",
          "client-side S3 multipart abort with metrics instrumentation"),
    Chunk("auth", "services/authz/check.py", 12, 38, "check_permission",
          "def check_permission(user, resource, action): return policy.evaluate(user, resource, action)",
          "central authorization gateway evaluating an OPA policy for user-resource-action"),
    Chunk("auth", "libs/policy/opa.py", 88, 110, "evaluate",
          "def evaluate(user, resource, action): return self.engine.query('authz', input=...)",
          "OPA policy engine query wrapper for authorization checks"),
    Chunk("catalog", "services/search/query.rs", 200, 240, "rank_fusion",
          "pub fn rank_fusion(dense: Vec<Hit>, sparse: Vec<Hit>) -> Vec<Hit>",
          "reciprocal rank fusion of dense and sparse retrieval results"),
]


# ----------------------------
# Tokenizer
# ----------------------------

# 重构：正则预编译成模块级常量。tokenize 每次检索都要被调很多遍，
# re.findall 每次都重新解析一遍模式字符串；而且原来「分词规则」在文件里
# 写了两遍（fake_embed 和 tokenize 各一个字符串字面量），改一处漏一处。
_WORD_RE = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    r"""切词。中英混排会被切成中文块 + 英文单词，对 BM25 够用。

    重构：原稿正则写成 r"w+"，漏了反斜杠，匹配的是「连续的小写字母 w」。
    于是任何 query 都被切成一串 "w"，BM25 退化成「谁正文里 w 多谁靠前」，
    三个完全不同的 query 的 sparse 结果一模一样。\w+ 才是「单词」。
    """
    return _WORD_RE.findall(text.lower())


# ----------------------------
# Embedding
# ----------------------------

# 重构：维度提成常量。原先 fake_embed / add / search 各自用默认参数 64，
# 谁哪天传了别的 dim，建索引的向量和查询向量长度就不一致。原稿用 zip 算点积，
# 长度不等是静默截断——相似度照样返回一个数，错得无声无息。改成 math.sumprod
# 之后这种不一致会直接 ValueError，再加上这个常量，两头都堵住。
_EMBED_DIM = 64


def _token_hash(token: str) -> int:
    """稳定的字符串哈希。

    重构：原稿用内置 hash()。CPython 里 str 的哈希每个进程加一次随机盐
    （PYTHONHASHSEED），同一个 chunk 换个进程就落进不同的桶：实测跑三次，
    dense 的排序是三种结果，demo 不可复现，也没法写断言。blake2b 是标准库里
    最快的稳定摘要之一，digest_size=8 正好装进 int。
    """
    digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def fake_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """把文本塞进 dim 维单位向量。假的，只为让 demo 不依赖模型权重。

    重构：原稿直接拿 norm 做除数。空文本（或全是标点）切不出 token，
    归一化时 ZeroDivisionError。零向量就是最诚实的答案：和谁都不相似。
    以后换成真 embedding，这个函数整个删掉，dim 由模型决定。
    """
    vec = [0.0] * dim
    for token in tokenize(text):
        h = _token_hash(token)
        vec[h % dim] += 1.0
        vec[(h >> 8) % dim] += 0.5

    norm = math.hypot(*vec)
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个单位向量的余弦相似度，就是点积。

    重构：原稿手写 sum(x * y for x, y in zip(a, b))。math.sumprod 就是点积
    （3.12+），C 实现，还省掉生成器的开销。注意这个简化只对已归一化的向量成立；
    以后接真模型、向量未必是单位长度时，改成 sumprod(a, b) / (hypot(a) * hypot(b))。
    """
    return math.sumprod(a, b)


@dataclass
class DenseIndex:
    vectors: list[tuple[Chunk, list[float]]] = field(default_factory=list)

    def add(self, chunk: Chunk) -> None:
        # symbol / summary / body 拼一段再 embed，想让 symbol 权重更高就在这里重复拼接。
        text = f"{chunk.symbol}\n{chunk.summary}\n{chunk.body}"
        self.vectors.append((chunk, fake_embed(text)))

    def search(self, query: str, k: int = 10) -> list[tuple[Chunk, float]]:
        query_vec = fake_embed(query)
        scored = [
            (chunk, cosine_similarity(query_vec, vec)) for chunk, vec in self.vectors
        ]
        # 重构：全文件统一成 itemgetter + reverse=True（这里原本就是这个写法，
        # 其它几处是 key=lambda x: -x[1]）。同一个意图只有一种写法，读的人不用
        # 每次确认「这个负号是不是有什么讲究」。
        return sorted(scored, key=itemgetter(1), reverse=True)[:k]


# ----------------------------
# BM25
# ----------------------------


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75
    docs: list[Chunk] = field(default_factory=list)
    doc_lens: list[int] = field(default_factory=list)
    df: Counter[str] = field(default_factory=Counter)
    tf: list[Counter[str]] = field(default_factory=list)
    avgdl: float = 0.0
    # 重构：文档总长度增量维护。原稿每次 add 都重扫一遍 sum(self.doc_lens)，
    # 灌 N 篇文档就是平方级，建索引的时间全花在这个求和上。
    # 新加的字段要在 add 里一起维护——这是「用空间换这一步的复杂度」。
    total_len: int = 0

    def add(self, chunk: Chunk) -> None:
        # 字段权重靠重复 token 实现（symbol ×4、summary ×2）。这是 demo 的简化；
        # 真要按字段调权重，改成「每个字段各建一张索引再线性组合」，别继续堆乘数。
        tokens = (
            tokenize(chunk.symbol) * 4
            + tokenize(chunk.summary) * 2
            + tokenize(chunk.body)
        )

        counts = Counter(tokens)
        self.docs.append(chunk)
        self.doc_lens.append(len(tokens))
        self.tf.append(counts)

        # 重构：原稿 for term in counts: self.df[term] += 1。df 是「文档频率」，
        # 每个 term 每篇文档只加 1，所以传的是 counts.keys()。
        # 直接传 counts 会把词频当文档频率加进去，idf 就废了（Counter.update 是相加）。
        self.df.update(counts.keys())

        self.total_len += len(tokens)
        self.avgdl = self.total_len / len(self.docs)

    def search(self, query: str, k: int = 10) -> list[tuple[Chunk, float]]:
        n = len(self.docs)
        scores = [0.0] * n

        for term in tokenize(query):
            df = self.df.get(term, 0)
            if df == 0:
                continue

            idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
            for i, counts in enumerate(self.tf):
                f = counts.get(term, 0)
                if f == 0:
                    continue
                dl = self.doc_lens[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * f * (self.k1 + 1) / denom

        # 重构：原稿这两行缩进在 for term 循环体里面，只用第一个命中的 query term
        # 排完序就 return，后面的 query term 全部丢掉；靠 s > 0 过滤后还常常不足 k 条。
        # 计分要等所有 term 都累加完再排序，这是 BM25 打分与「取 top-k」的分界线。
        # 以后语料变大，把内层扫全表的循环换成倒排表 posting list，只遍历命中的文档。
        ranked = sorted(zip(self.docs, scores), key=itemgetter(1), reverse=True)
        return [(chunk, score) for chunk, score in ranked[:k] if score > 0]


# ----------------------------
# Fusion
# ----------------------------


def rrf(
    dense: list[tuple[Chunk, float]],
    sparse: list[tuple[Chunk, float]],
    k_rrf: int = 60,
) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion：只看名次，不看两路的分数量纲。

    重构：原来的两段累加只差一个列表来源，合成一次循环遍历 (dense, sparse)。
    60 来自原论文，作用是压平名次之间的差距；dense 的余弦和 BM25 的分数
    不可比，所以按名次融合比按分数加权稳。
    """
    score: dict[str, float] = defaultdict(float)
    by_anchor: dict[str, Chunk] = {}

    for hits in (dense, sparse):
        for rank, (chunk, _) in enumerate(hits):
            score[chunk.anchor] += 1.0 / (k_rrf + rank + 1)
            by_anchor[chunk.anchor] = chunk

    fused = sorted(score.items(), key=itemgetter(1), reverse=True)
    return [(by_anchor[anchor], s) for anchor, s in fused]


# ----------------------------
# Reranker
# ----------------------------

# 重构：权重提成具名常量。原稿是 0.3 * (len(...) * 3)，两层系数绕了一圈，
# 实际 symbol 权重是 0.9、summary 是 0.1，看表达式根本看不出来。调权重只动这两行。
RERANK_SYMBOL_WEIGHT = 0.9
RERANK_SUMMARY_WEIGHT = 0.1


def rerank(
    query: str,
    candidates: list[tuple[Chunk, float]],
    top_k: int = 5,
) -> list[tuple[Chunk, float]]:
    """在融合结果上再打一次分：query 与 symbol / summary 的词面重叠。

    重构：这是「重排」，不是「召回」——只重排传进来的 candidates，不自己再拉一遍索引，
    所以它接受任意来源的候选。以后换成 cross-encoder 模型，替换函数体即可，
    调用方不用改。
    """
    query_tokens = set(tokenize(query))

    out: list[tuple[Chunk, float]] = []
    for chunk, prior in candidates:
        symbol_overlap = len(query_tokens & set(tokenize(chunk.symbol)))
        summary_overlap = len(query_tokens & set(tokenize(chunk.summary)))
        rerank_score = (
            prior
            + RERANK_SYMBOL_WEIGHT * symbol_overlap
            + RERANK_SUMMARY_WEIGHT * summary_overlap
        )
        out.append((chunk, rerank_score))

    out.sort(key=itemgetter(1), reverse=True)
    return out[:top_k]


# ----------------------------
# Orchestrator
# ----------------------------


class Answer(TypedDict):
    """answer() 的返回结构。

    重构：原稿标注 dict[str, object]——键值类型全糊在一起，取值靠字符串下标，
    拼错 result["qury"] 要到那一行运行时才炸，类型检查完全帮不上。TypedDict
    把键和值的类型写在定义处，运行时零开销，就是普通 dict。
    """

    query: str
    dense_top: list[str]
    sparse_top: list[str]
    fused_top: list[str]
    rerank_top: list[str]


def _anchors(hits: list[tuple[Chunk, float]], limit: int | None = None) -> list[str]:
    """取某个阶段的 citation。limit=None 表示全部。

    重构：原稿在 answer() 里把 [c.anchor for c, _ in ...] 写了四遍，每处长度还不一样。
    """
    selected = hits if limit is None else hits[:limit]
    return [chunk.anchor for chunk, _ in selected]


def answer(query: str, dense: DenseIndex, bm25: BM25Index) -> Answer:
    """两路召回 → RRF 融合 → 重排。

    这里把每一层的中间结果都返回来，是为了教学时能看出各层的贡献。
    真上线只返回 rerank_top，前面几个键删掉；召回数量（10 / 5）也是 demo 尺度。
    """
    dense_hits = dense.search(query, k=10)
    bm25_hits = bm25.search(query, k=10)

    fused = rrf(dense_hits, bm25_hits)
    top = rerank(query, fused, top_k=5)

    return Answer(
        query=query,
        dense_top=_anchors(dense_hits, 3),
        sparse_top=_anchors(bm25_hits, 3),
        fused_top=_anchors(fused, 5),
        rerank_top=_anchors(top),
    )


def main() -> None:
    dense = DenseIndex()
    bm25 = BM25Index()

    for chunk in SAMPLE_CORPUS:
        dense.add(chunk)
        bm25.add(chunk)

    # 重构：原稿打印 f"Q: {result['query']}"，绕回结果里取了一遍循环变量本身。
    # 这里直接打 query；结果里的 query 键留给「结果离开这个循环之后」的场景。
    for query in (
        "how is S3 multipart abort wired into retry budget",
        "where is authorization centralized",
        "how does rank fusion work",
    ):
        result = answer(query, dense, bm25)
        print(f"Q: {query}")
        print(f"  dense  : {result['dense_top']}")
        print(f"  sparse : {result['sparse_top']}")
        print(f"  fused  : {result['fused_top']}")
        print(f"  rerank : {result['rerank_top']}")
        print()


if __name__ == "__main__":
    main()
