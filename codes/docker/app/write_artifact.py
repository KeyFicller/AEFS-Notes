"""写一个假的 embedding 矩阵，用来观察卷是否持久。"""

from pathlib import Path

import numpy as np


if __name__ == "__main__":
    out = Path("/artifacts")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "embeddings.npy"
    np.save(path, np.random.default_rng(0).normal(size=(4, 8)))
    print("wrote", path, path.stat().st_size, "bytes")
