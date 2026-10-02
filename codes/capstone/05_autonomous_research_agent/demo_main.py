"""Autonomous research agent — plan/execute/verify tree search scaffold.

The hard architectural primitive is best-first tree search over experiment
nodes with budgeted expansion, per-node sandboxed execution, and a weighted
novelty / quality / budget score. The LLM planner and the actual PyTorch
experiments are stubbed so the tree-search skeleton is observable end to end
without real compute.

Run:  python demo_main.py

搜「重构：」可以跳到每一处改动。注释写的是「为什么这样改」和「以后怎么接」，
不是复述代码在做什么。
"""

# 重构：import 原来夹在第一个分节标题底下。__future__ 得是 docstring 之后的第一条
# 语句，标准库 import 也习惯排在所有分节之前、按模块名排序。整块提上来。
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from operator import attrgetter


# --------------------------------------------------
# Experiment node
# --------------------------------------------------

# 重构：权重从 score() 里提成具名常量。原来 0.4 / 0.5 / 0.1 是三个裸字面量，
# 看 `novelty * 0.4 + quality * 0.5 + ...` 要读完才知道它们和为 1。调权重只动这几行。
WEIGHT_NOVELTY = 0.4
WEIGHT_QUALITY = 0.5
WEIGHT_BUDGET = 0.1
# 剩余预算到这个量级时 budget 项就加满（min 到 1.0）。30 美元预算下它一直是满的，
# 所以真正让不同节点分出来的是 novelty 和 quality。
BUDGET_SCALE_USD = 10.0


@dataclass
class Node:
    node_id: int
    parent: int | None
    hypothesis: str
    config: dict[str, object]
    result: dict[str, float] = field(default_factory=dict)
    cost_usd: float = 0.0
    novelty: float = 0.5
    quality: float = 0.0
    failure: str | None = None

    def score(self, remaining_budget: float) -> float:
        """给「下一步展开哪个节点」排序的分。

        重构：顶部 docstring 说的是 novelty × quality × budget（连乘）。
        真按连乘写，任何一项为 0 就把整条分支打成 0（还没量出 quality 的节点更是必然为 0）；
        加权和没有这个塌缩，也方便调权重。文档和实现不一致时改注释，不要改代码去迁就注释。
        权重和为 1，所以分数量级就是 0..1。
        """
        budget_weight = min(1.0, remaining_budget / BUDGET_SCALE_USD)
        return (
            self.novelty * WEIGHT_NOVELTY
            + self.quality * WEIGHT_QUALITY
            + budget_weight * WEIGHT_BUDGET
        )


# --------------------------------------------------
# Stub planner
# --------------------------------------------------

def expand(node: Node, next_id: int) -> list[Node]:
    """Propose children by varying one config dimension at a time.

    重构：删掉 `base_cfg = node.config` 这层别名，直接 dict(node.config, ...)。
    每次 small-edit 只动一个维度、另一个从父节点继承，这是「扩张」的定义；
    expand 只负责「怎么改」，改完跑不跑由 tree_search 按预算决定。
    接真 planner（LLM 提假设）时替换函数体即可，调用方不用动。

    id 由调用方传进来、在这里连续发号，调用方再 `next_id += len(children)`。
    这是刻意的：node_id 全局唯一，发号必须只有一处，别让 expand 自己维护计数器。
    """
    children: list[Node] = []
    for sp in (4, 8, 16):
        children.append(Node(
            node_id=next_id,
            parent=node.node_id,
            hypothesis=f"sparsity top-{sp}",
            config=dict(node.config, sparsity_top=sp),
        ))
        next_id += 1
    for lr in (3e-4, 1e-3):
        children.append(Node(
            node_id=next_id,
            parent=node.node_id,
            hypothesis=f"lr={lr}",
            config=dict(node.config, lr=lr),
        ))
        next_id += 1
    return children


# --------------------------------------------------
# Sandbox execution
# --------------------------------------------------

def run_experiment(node: Node, rng: random.Random) -> None:
    """Simulates running the experiment in a sandboxed container.
    A real build shells out to:
      docker run --network=none --memory=8g --cpus=2 --read-only ...
    and captures stdout + metrics files from a mounted output volume.

    重构：`0.0001 * abs(lr - 3e-4) * 1000` 是三个常数相乘，实际就等于
    `0.1 * abs(lr - 3e-4)`。绕这一圈会让人以为 lr 的系数是 1e-4，合并成字面量。
    另外 config 是 dict[str, object]，算术前显式转 int / float，类型检查器才看得懂；
    真实验里这两个值来自实验配置，本来就有确定类型。
    """
    sp = int(node.config.get("sparsity_top", 8))
    lr = float(node.config.get("lr", 3e-4))

    ideal_sp = 8
    loss = 3.0 - 0.3 * (1 - abs(sp - ideal_sp) / 16) + rng.gauss(0, 0.05)
    loss += 0.1 * abs(lr - 3e-4)

    node.result = {"loss": round(loss, 3), "sparsity_top": sp, "lr": lr}
    node.cost_usd = 1.2 + rng.uniform(0, 0.4)
    node.quality = max(0.0, 1.0 - (loss - 2.5) / 1.5)
    node.novelty = 0.5 + rng.uniform(-0.1, 0.2)

    if rng.random() < 0.1:
        node.failure = "oom_killed_by_cgroup"
        node.quality = 0.0


# --------------------------------------------------
# verify step
# --------------------------------------------------

def verify(node: Node) -> bool:
    """把一个节点放行到 frontier 前的体检。

    重构：`loss > 4.0` 这条在本 demo 里永远不会命中——stub 的 loss 值域大约
    [2.7, 3.2]，够不到 4.0。保留它，因为真跑起来 loss 是会发散的；但要清楚
    它现在是条没被覆盖过的分支，别当已测试路径。返回值只用来表达 ok/不 ok，
    调用方真正要的是副作用（写 node.failure）。
    """
    if node.failure:
        return False

    if node.result.get("loss", 99) > 4.0:
        node.failure = "loss_diverged"
        return False

    return True


# --------------------------------------------------
# Tree Search
# --------------------------------------------------

@dataclass
class Tree:
    root: Node
    nodes: dict[int, Node] = field(default_factory=dict)
    # 重构：frontier 原来只标了 list，没写元素类型。它装的是 heapq 的三元组
    # (负分, 插入序号, node_id)；取负是为了拿最小堆当最大堆。类型写出来，
    # 下一个人改 push/pop 时不用回头猜。
    frontier: list[tuple[float, int, int]] = field(default_factory=list)
    counter: int = 0
    budget: float = 30.0
    spent: float = 0.0
    # 重构：原来叫 max_nodes，数的是「生成过」的节点。可一次 expand 就生成 5 个孩子，
    # 于是上限 24 在只跑完 4 个实验后就撑爆（实测 nodes=26、真跑的实验只有 4 个），
    # 树永远停在两层、30 美元预算也永远花不完（实测只花 $5.57）。现在这个上限数的是
    # 「跑过」的节点，改名说清楚。见 tree_search 里「先跑后压」的注释。
    max_experiments: int = 24

    def push(self, node: Node) -> None:
        self.nodes[node.node_id] = node
        self.counter += 1
        remaining = self.budget - self.spent
        heapq.heappush(self.frontier, (-node.score(remaining), self.counter, node.node_id))

    def pop(self) -> Node | None:
        # 重构：原稿是 `while self.frontier: ... return ...`——循环体第一句就 return，
        # 从第二次迭代起 while 没有意义，读的人还要停下来确认不是死循环。就是个 if。
        if not self.frontier:
            return None
        _, _, node_id = heapq.heappop(self.frontier)
        return self.nodes[node_id]


def log_experiment(node: Node, spent: float) -> None:
    """打印一个实验节点。seed baseline 和它的子节点共用同一行格式。"""
    flag = "FAIL" if node.failure else "ok "
    loss = node.result.get("loss", "?")
    print(f"    [{flag}] node #{node.node_id:02d}  hypo='{node.hypothesis}'  "
          f"loss={loss:>5}  $={node.cost_usd:.2f}  cum=${spent:.2f}")


def tree_search(seed: str, rng: random.Random) -> Tree:
    """Best-first: 跑孩子 -> 按实测分压堆 -> 弹出最高分的节点继续扩张。

    重构（本文件最大的一处）：原稿是「pop 一个节点 → 跑它 → 再 expand」。
    pop 出来跑出的 quality 只写在这个已经出堆的节点上；它的孩子进堆时 quality
    还是默认 0，novelty 也还是默认 0.5，于是所有兄弟节点同分、堆序退化成插入
    顺序——号称 best-first，实测是 BFS。现在把顺序反过来：expand 出孩子后先逐个
    跑出真实的 quality / novelty，再压进 frontier。这样 pop 出来的才是「已评估
    节点里最值得展开的那个」，best-first 才成立。

    代价：一次扩张会把该节点的所有孩子都跑掉（真实验里就是 fan-out 并行），
    而不是每 pop 一次只跑一个。想省预算可以在内层循环里按预估成本挑几个跑。
    """
    root = Node(
        node_id=0,
        parent=None,
        hypothesis=seed,
        config={"sparsity_top": 8, "lr": 3e-4},
    )
    tree = Tree(root=root)

    # 重构：原稿用 `if cur.node_id != 0` 跳过 root，于是 seed 从没被跑过：result 是空的，
    # best_branch 打出来是 `loss=?  q=0.50` 的幽灵节点，那个 0.50 还是写死的、不是量出来的。
    # seed 本身就是一次实验（baseline），先跑它、记结果，再把 root 压进 frontier。
    run_experiment(root, rng)
    root.novelty = 1.0  # seed 的 novelty 定义为 1：还没有任何已评估节点覆盖它
    tree.spent += root.cost_usd
    tree.push(root)
    log_experiment(root, tree.spent)

    next_id = 1
    while tree.frontier and len(tree.nodes) < tree.max_experiments:
        cur = tree.pop()
        if cur is None:
            break

        # 重构：失败节点不再展开。在失败的假设上继续花钱等于拿失败当地基；
        # 它已经带 failure 了，best_branch 也会把它过滤掉。
        if cur.failure:
            continue

        if tree.spent >= tree.budget:
            print(f"    BUDGET EXHAUSTED at ${tree.spent:.2f}")
            break

        children = expand(cur, next_id)
        next_id += len(children)

        for child in children:
            # 预算和实验数都在「跑之前」判，所以不会拿一次超支的实验去撞线。
            if len(tree.nodes) >= tree.max_experiments or tree.spent >= tree.budget:
                break
            run_experiment(child, rng)
            tree.spent += child.cost_usd
            verify(child)
            tree.push(child)
            log_experiment(child, tree.spent)

    return tree


# --------------------------------------------------
# Best branch
# --------------------------------------------------

def best_branch(tree: Tree) -> list[Node]:
    """质量最好的已完成叶子节点，再一路回溯到 root。

    重构：key 从 `lambda n : n.quality` 换成 attrgetter("quality")，顺带修掉
    `n :` 那个 PEP 8 不该有的空格。这里按 quality 选分支，不是按 Node.score：
    score 里的 novelty 和 budget 项是给「下一步展开谁」用的，写报告只关心这条
    分支做出来的质量。两个「最好」不是一回事，别混用同一个函数。
    """
    done = [n for n in tree.nodes.values() if n.result and not n.failure]

    if not done:
        return []

    best = max(done, key=attrgetter("quality"))

    chain = [best]
    while chain[-1].parent is not None:
        chain.append(tree.nodes[chain[-1].parent])

    return list(reversed(chain))


# --------------------------------------------------
# Main
# --------------------------------------------------

def main() -> None:
    print("=== autonomous research agent: tree search (budget $30) ===")

    rng = random.Random(7)
    seed = "investigate sparsity patterns in attention maps of sub-1B transformers"

    tree = tree_search(seed, rng)

    print()
    print(f"experiments run: {len(tree.nodes)}")
    print(f"budget spent   : ${tree.spent:.2f} of ${tree.budget:.2f}")
    print(f"failed nodes   : {sum(1 for n in tree.nodes.values() if n.failure)}")

    branch = best_branch(tree)
    print(f"\nbest branch (length {len(branch)}):")
    for n in branch:
        loss = n.result.get("loss", "?")
        print(f"  #{n.node_id:02d} {n.hypothesis}   q={n.quality:.2f}  loss={loss}")

    print("\n(writer + reviewer + red-team steps would run here; "
          "stubbed for the scaffold)")


if __name__ == "__main__":
    main()
