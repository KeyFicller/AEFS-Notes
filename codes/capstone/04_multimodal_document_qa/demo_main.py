"""

Multimodal Document QA

"""

from dataclasses import dataclass, field
from pydoc import pager
import re
import random
import math

# --------------------------------------------------
# Patch Embedding
# --------------------------------------------------

EMB_DIM = 16

def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())

def hash_embed(tok: str) -> list[float]:
    rnd = random.Random(hash(tok) & 0xFFFFFFFF)
    v = [rnd.gauss(0, 1) for _ in range(EMB_DIM)]
    n = math.sqrt(sum(x ** 2 for x in v))
    return [x / n for x in v]

@dataclass
class Page:
    doc_id : str
    page_num : int
    content_tokens: list[str]
    patches: list[list[float]] = field(default_factory=list)

    def embed_patches(self) -> None:
        self.patches = [
            hash_embed(tok) for tok in self.content_tokens
        ]

# --------------------------------------------------
# Doc Pruner -- dropout low-signal patches
# --------------------------------------------------

def doc_prune(patches: list[list[float]], keep_fraction: float = 0.5) -> list[list[float]]:
    scored = [(sum(abs(x) for x in p), p) for p in patches]
    scored.sort(key=lambda x: -x[0])
    keep_n = max(1, int(len(scored) * keep_fraction))
    return [p for _, p in scored[:keep_n]]

# --------------------------------------------------
# MaxSim late interation
# --------------------------------------------------

def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

def max_sim_score(
    query_tokens: list[list[float]],
    doc_patches: list[list[float]]
):
    total = 0.0
    for q in query_tokens:
        best = max(
            dot(q, p) for p in doc_patches
        )
        total += best
    return total

# --------------------------------------------------
# Index + Retrieval --- Ranked top-k by MaxSim
# --------------------------------------------------

@dataclass
class Index:
    pages: list[Page] = field(default_factory=list)

    def add(self, page: Page) -> None:
        self.pages.append(page)

    def retrieve(self, query: str, k: int = 8) -> list[tuple[Page, float]]:
        q_tokens = [hash_embed(t) for t in query]
        scored = [(pg, max_sim_score(q_tokens, pg.patches)) for pg in self.pages]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

# --------------------------------------------------
# Synthetic Corpus
# --------------------------------------------------

CORPUS = [
    ("10k-2024", 88, "segment EMEA operating margin 18.2 to 16.8 decline 140bp table four"),
    ("10k-2024", 92, "MDA operating performance EMEA macro headwinds FX impact narrative"),
    ("10k-2024", 14, "executive summary revenue growth 7 percent consolidated totals"),
    ("paper-vidore-v3", 3, "late interaction multi vector retrieval ColPali ColQwen benchmark"),
    ("paper-vidore-v3", 7, "nDCG results table vision first vs OCR then text columns"),
    ("paper-m3docrag", 2, "M3DocVQA multi page reasoning evaluation protocol"),
    ("handwritten-lab", 5, "experiment notes circuit board pH readings handwritten"),
    ("handwritten-lab", 6, "graph with annotated error bars figure 3 caption"),
    ("chart-report", 11, "line chart revenue by segment EMEA americas APAC Q1 Q4"),
    ("chart-report", 12, "bar chart operating margin by segment with 2023 2024 comparison"),
]

def build_index(prune: bool = True) -> Index:
    idx = Index()
    for doc, page, text in CORPUS:
        p = Page(doc_id = doc, page_num = page, content_tokens= tokenize(text))
        p.embed_patches()
        if prune:
            p.patches = doc_prune(p.patches, keep_fraction=0.5)
        idx.add(p)

    return idx

def main() -> None:
    print("=== build index with DocPruner (50% patches) ====")
    idx = build_index(prune=True)
    print(f"pages indexed: {len(idx.pages)}")

    queries = [
        "what was the 2024 operating margin change for EMEA",
        "late interaction retrieval vs OCR",
        "handwritten experiemental figures with error bars",
        "bar chart comparing segment margins"
    ]

    for q in queries:
        print(f"\Q: {q}")
        hits = idx.retrieve(q, k = 3)
        for pg, score in hits:
            print(f"   score={score:+.3f} {pg.doc_id} p.{pg.page_num}")

    
    # pruning ablation
    print("\n=== ablation: pruning off vs on ===")
    full = build_index(prune=False)
    pruned = build_index(prune=True)
    q = "chart comparing segment margins"
    full_top = [(p.doc_id, p.page_num) for p, _ in full.retrieve(q, 3)]
    prn_top = [(p.doc_id, p.page_num) for p, _ in pruned.retrieve(q, 3)]
    print(f"  full    top-3 : {full_top}")
    print(f"  pruned  top-3 : {prn_top}")
    print(f"  overlap       : {len(set(full_top) & set(prn_top))}/3")


if __name__ == "__main__":
    main()
