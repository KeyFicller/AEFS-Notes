"""镜像里的最小 AI 依赖检查：版本 + 一次余弦相似度。"""

import platform
import sys

import numpy as np


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    query = np.array([0.9, 0.1, 0.0])
    doc_a = np.array([1.0, 0.0, 0.0])
    doc_b = np.array([0.0, 1.0, 0.0])

    print("python", sys.version.split()[0])
    print("numpy", np.__version__)
    print("arch", platform.machine())
    print("cos(query, doc_a)", round(cosine(query, doc_a), 3))
    print("cos(query, doc_b)", round(cosine(query, doc_b), 3))
