#!/usr/bin/env bash
# 校验 app/ 里的练习环境：镜像能跑、层顺序对、卷能持久、compose 能连通。
# 需要 Docker Desktop 在跑。全量跑一遍约 1~2 分钟。
set -euo pipefail

cd "$(dirname "$0")"
backup=""
restore() { [ -n "$backup" ] && cp "$backup" app/main.py; }
cleanup() {
  restore
  docker compose -f app/compose.yaml down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# 某一步（如 RUN pip install）是否命中缓存。BuildKit 把 CACHED 打在单独一行。
cached() {
  local id
  id=$(grep -m1 "$2" <<<"$1" | grep -o '^#[0-9]*' || true)
  [ -n "$id" ] && grep -qF "$id CACHED" <<<"$1"
}

backup=$(mktemp)
cp app/main.py "$backup"

echo "1/5 镜像能跑"
docker build -q -t docker-lab:check app >/dev/null
out=$(docker run --rm docker-lab:check)
grep -q 'numpy 2.1.3' <<<"$out" || fail "镜像里没有 numpy 2.1.3"
grep -q 'arch' <<<"$out" || fail "main.py 没输出 arch"

echo "2/5 先装依赖再拷代码，改代码后 pip 仍命中缓存"
printf '\n# cache check\n' >> app/main.py
log=$(docker build -t docker-lab:check app 2>&1)
cached "$log" 'RUN pip install' || fail "好 Dockerfile 的 pip 层没命中缓存"
cp "$backup" app/main.py

echo "3/5 COPY . . 放前面，改代码后 pip 必须重跑"
docker build -f app/Dockerfile.bad -t docker-lab:check-bad app >/dev/null 2>&1
printf '\n# cache check\n' >> app/main.py
log=$(docker build -f app/Dockerfile.bad -t docker-lab:check-bad app 2>&1)
cached "$log" 'RUN pip install' && fail "坏 Dockerfile 的 pip 层竟然命中缓存"
cp "$backup" app/main.py

echo "4/5 卷把文件写回宿主机"
rm -rf artifacts && mkdir -p artifacts
docker run --rm -v "$PWD/artifacts:/artifacts" docker-lab:check python write_artifact.py >/dev/null
test -s artifacts/embeddings.npy || fail "卷没有把文件写回宿主机"

echo "5/5 compose：服务名可解析，down 保留命名卷，down -v 清掉"
docker compose -f app/compose.yaml up -d >/dev/null 2>&1
sleep 3
docker compose -f app/compose.yaml exec -T lab python -c "import socket; socket.gethostbyname('cache')" >/dev/null \
  || fail "lab 解析不到 cache"
docker compose -f app/compose.yaml exec -T cache redis-cli set k v >/dev/null
docker compose -f app/compose.yaml down >/dev/null 2>&1
docker compose -f app/compose.yaml up -d >/dev/null 2>&1
sleep 3
test "$(docker compose -f app/compose.yaml exec -T cache redis-cli get k)" = "v" \
  || fail "down 之后命名卷丢了"
docker compose -f app/compose.yaml down -v >/dev/null 2>&1
docker compose -f app/compose.yaml up -d >/dev/null 2>&1
sleep 3
test -z "$(docker compose -f app/compose.yaml exec -T cache redis-cli get k)" \
  || fail "down -v 之后键还在"

rm -rf artifacts
echo "PASS"
