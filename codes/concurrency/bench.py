"""并发练习的两块负载：一块烧 CPU，一块只是等。

函数必须放在可导入的模块里。macOS 的进程池用 spawn 起子进程，子进程会重新
import 这个模块；写在笔记本单元格里的函数拿不到，会报 AttributeError。
"""

import time

N = 4_000_000


def cpu_work(n: int = N) -> int:
    """纯 Python 整数运算，全程持有 GIL。"""
    total = 0
    for i in range(n):
        total = (total * 31 + i) % 1_000_003
    return total


def io_work(seconds: float = 0.2) -> str:
    """模拟一次网络请求：占着线程等，不烧 CPU。"""
    time.sleep(seconds)
    return "ok"
