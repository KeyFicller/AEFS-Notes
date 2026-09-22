# Python 常用标准库

随解释器自带，不用 `pip install`。

练习放在 `python_base/{模块名}/qa.ipynb`。需要读写文件时，工作空间就是该目录。

| 模块 | 用途 |
| --- | --- |
| `pathlib` | 拼路径、读写文件 |
| `os` | 环境变量、当前目录、和操作系统打交道 |
| `sys` | 命令行参数、模块搜索路径、退出码 |
| `argparse` | 解析命令行参数 |
| `subprocess` | 启动外部程序，拿到输出和退出码 |
| `shutil` | 复制、移动、删除目录树 |
| `json` | 读写 JSON |
| `csv` | 读写 CSV |
| `re` | 正则匹配和替换 |
| `datetime` | 日期和时间 |
| `collections` | `Counter`、`defaultdict`、`deque` |
| `itertools` | 排列、分组、链式迭代 |
| `functools` | `partial`、`lru_cache` |
| `dataclasses` | 用字段声明数据类 |
| `enum` | 一组有名字的常量 |
| `typing` | 类型标注 |
| `logging` | 分级日志 |
| `math` | 数学函数 |
| `random` | 伪随机数 |
| `hashlib` | 摘要，如 SHA-256 |
| `sqlite3` | 内置 SQLite |
| `urllib.request` | 发简单 HTTP 请求 |
| `tempfile` | 临时文件和目录 |
| `concurrent.futures` | 线程池、进程池 |
| `asyncio` | 异步 I/O |
| `unittest` | 单元测试 |
