#!/usr/bin/env bash
# 用 PATH 里的 bash 跑本脚本（不写死 /bin/bash，方便 macOS / Linux）。

# -e：任一命令失败立刻退出
# -u：用了未定义变量就报错
# -o pipefail：管道里任一环失败，整条管道算失败
set -euo pipefail

# 把本 pack 装进「当前工作目录」那个仓库。
# 用法：在目标仓库根目录执行  path/to/bin/install.sh
#       已有 AGENTS.md 时加 --force 才覆盖。

# "${1:-}" = 第 1 个参数；没传则为空字符串（避免 set -u 炸）
FORCE="${1:-}"

# 装到哪里：调用时的当前目录（所以要先 cd 到目标仓库再跑）
TARGET="$(pwd)"

# "$0" 是本脚本路径；dirname 得到 bin/；再 .. 到 pack 根目录。
# 外层 cd + pwd 把相对路径收成绝对路径，后面 cp 不依赖你从哪调用。
PACK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 安装前先确认 pack 自己是完整的，缺源文件就别半装。
required=("AGENTS.md" "VERSION" "docs" "schemas" "scripts")
for path in "${required[@]}"; do
    # -e：文件或目录存在即可
    if [[ ! -e "$PACK_ROOT/$path" ]]; then
        # >&2 打到 stderr，方便和正常输出分开
        echo "missing pack source: $PACK_ROOT/$path" >&2
        exit 1
    fi
done

# 目标仓库已有 AGENTS.md，且没说 --force：拒绝覆盖，避免 silently 毁掉现有路由。
if [[ -e "$TARGET/AGENTS.md" && "$FORCE" != "--force" ]]; then
    echo "AGENTS.md already exists. Pass --force to overwrite." >&2
    exit 1
fi

cp "$PACK_ROOT/AGENTS.md" "$TARGET/AGENTS.md"

# -p：目录已存在也不报错
mkdir -p "$TARGET/docs" "$TARGET/schemas" "$TARGET/scripts"

# "src/." 表示复制目录「里面的内容」到目标，而不是再套一层同名文件夹
cp -r "$PACK_ROOT/docs/." "$TARGET/docs/"
cp -r "$PACK_ROOT/schemas/." "$TARGET/schemas/"
cp -r "$PACK_ROOT/scripts/." "$TARGET/scripts/"

# 记下装进去的 pack 版本，方便以后对照升级
cat "$PACK_ROOT/VERSION" > "$TARGET/.workbench-version"

echo "pack installed at version $(cat "$PACK_ROOT/VERSION")"
echo "next: edit task_board.json, set acceptance commands, run scripts/init_agent.py"
