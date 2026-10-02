"""生产版实时语音助手：真麦克风 + Silero VAD + faster-whisper + DeepSeek 流式 + 抢话。

demo_main.py 用 20ms 假帧把调度器跑通；这里把每一层换成真的，只留一个
「用 wav 代替麦克风」的自检开关（CI 和无声环境没有输入设备）。

和 demo_main.py 的对应：
- Frame / synth_call          -> MicSource：sounddevice 回调，16kHz 单声道真帧流
- Frame.is_speech             -> SileroVad：真 VAD（每块 512 采样 / 32ms）
- Frame.partial               -> Asr：faster-whisper 反复重转增长中的语音缓冲
- turn_completion_score       -> 继续用 demo_main 的启发式。LiveKit 那套 turn detector
                                 是独立模型，本项目不装
- run_session 手写状态机       -> 协程调度器 + create_agent（LangChain，底层 LangGraph）
- llm_stream_started_at = 140 -> 真流式首 token，实测 TTFT
- WEATHER 写死 420ms          -> 真 @tool：zoneinfo 查时区、wttr.in 查天气
- filler_emitted 计时          -> 首句没赶上 FILLER_AFTER_MS 就先垫一句
- barge_in_at_ms（写死）       -> 真抢话：出声时听到人声就 kill say + cancel agent task
- Metrics                     -> 全部 time.monotonic() 实测

诚实说明（和 01 里「PyTorch 不在这条链路里」、02 里「DeepSeek 没有 embeddings」同类）：

1. 扬声器外放会自激：TTS 的声音被自己的麦克风收进去，VAD 判成人声，立刻误触发抢话。
   生产靠 AEC 或耳机。**跑之前戴上耳机**；不想戴用 --no-barge-in（半双工：出声时
   丢弃麦克风输入，代价是没有打断能力）。
2. faster-whisper 不是流式模型。partial 只能靠反复重转整段缓冲来假装流式。
   base + int8 在 CPU 上是 0.4 倍实时（实测 1.46 秒音频转 0.63 秒），一句三秒的话
   按 480ms 一拍重转，累加起来是实时量级的算力，换来的却只是用来打印的中间结果，
   所以默认关掉（--partials 才开）。真流式 ASR（Deepgram Nova-3 之类）才值得开
   partial，替换点是 Asr 这一个类。
3. 判定「这句说完」之后要等一次全量转写（WAITING 窗口），这期间的音频按半双工丢弃。
   窗口百毫秒量级（0.4 倍实时），落在用户刚停口的位置，实际丢的多是静音；
   接流式 ASR 后这个窗口消失。
4. Asr 用 asyncio.to_thread 跑，不阻塞事件循环，但吃的是同一台机器的 CPU，
   和 TTS、LLM 抢核心。实测（11 秒音频 3 轮对话，关不关 partial 都一样）：
   帧循环落后墙钟 650~760ms，约 6%。MIC_QUEUE_MAX 给的是 2 秒余量，撑得住；
   再长就得把 ASR 挪到独立进程或独立服务——这正是 Metrics.lag_ms 要盯的数。
5. whisper 对很短的片段会幻觉出无关内容（实测对一小段音频吐出过
   「Приятного аппетита!」）。partial 默认关闭顺带压掉了大部分这类杂质；
   要根治就把 no_speech_threshold 收紧，或者用带置信度的流式 ASR。
6. TTS 用 macOS 自带的 say：真系统 TTS、零依赖、进程能被 kill，正好演示取消。
   换 ElevenLabs / Cartesia 只改 Speaker._argv，调度点一个不动。
7. 静音阈值和 turn 分数仍是启发式，见 demo_main。turn_score 里那层中文兜底是因为
   demo 的启发式按空白切词、标点表只有半角，中文整句会永远判成「没说完」——
   实测踩到过。VAD 只回答「有没有人声」，「这句说完没有」是另一个模型的问题。
8. 首包音频延迟里含 say 的进程启动（实测百毫秒量级），不是纯 TTS 模型延迟。
   垫话也会被算进首包音频，因为那确实是用户听到的第一个声音。

用法：
    python prod_main.py                 # 真麦克风，戴耳机
    python prod_main.py --seconds 30    # 30 秒后自动收尾
    python prod_main.py --wav q.wav     # 无声卡自检：按实时节奏喂 wav
    python prod_main.py --tts file      # 不发声，逐句合成到 tts_out/
    python prod_main.py --partials      # 打开重转式 partial

首次运行会下 faster-whisper 的 base 模型（约 145MB，走 hf-mirror）。想换小/换准：
VOICE_ASR_MODEL=tiny 或 small。语速和音色：VOICE_TTS_VOICE（默认 Tingting）。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import re
import sys
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from zoneinfo import ZoneInfo

# 必须在 import faster_whisper / huggingface_hub 之前设。huggingface_hub 在 import
# 那一刻就把 ENDPOINT 定死，之后再改环境变量不生效（02 里踩过同一个坑）。
# 国内直连 huggingface.co 会超时；你自己设了 HF_ENDPOINT 就以你为准。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import httpx  # noqa: E402
import numpy as np  # noqa: E402

# common.py 在上一级（codes/capstone/），脚本直接跑时要自己补路径。
_CAPSTONE = Path(__file__).resolve().parents[1]
if str(_CAPSTONE) not in sys.path:
    sys.path.insert(0, str(_CAPSTONE))

from common import load_local_env  # noqa: E402
from demo_main import SENTENCE_END_SCORE, turn_completion_score  # noqa: E402

from langchain.agents import create_agent  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_deepseek import ChatDeepSeek  # noqa: E402

# ----------------------------
# 参数
# ----------------------------

SAMPLE_RATE = 16_000
# Silero v5 在 16k 下按 512 采样一块推理，正好 32ms。块长是 VAD、ASR、时钟三者的公约数。
VAD_BLOCK = 512
BLOCK_MS = VAD_BLOCK * 1000 // SAMPLE_RATE
VAD_THRESHOLD = 0.5
MIC_QUEUE_MAX = 64  # 约 2 秒。积多了说明处理不过来，宁可丢帧也不能越追越旧

SILENCE_TRIGGER_MS = 500  # 静音攒这么久才去问 turn detector
# 0.55 是 demo 阈值表里「3 个词/字以上」那一档。demo 原稿取 0.6 是把「3 到 5 个词」
# 整档当没说完，英文里合理（三个词确实可能是半句），中文里会把「現在幾點」这种
# 正常短问句全挡掉——实测就是这么一直不接话的。
TURN_SCORE_THRESHOLD = 0.55
ASR_INTERVAL_MS = 480  # partial 重转间隔
MIN_UTTERANCE_MS = 320  # 短于这个不转写，省算力也避免把咳嗽转成字
MAX_UTTERANCE_MS = 30_000  # 单句上限，防止有人对着麦一直说把缓冲撑爆

FILLER_AFTER_MS = 700  # 首句超过这么久没准备好就垫一句
FILLER_TEXT = "嗯，我看一下。"
MIN_SENTENCE_CHARS = 4  # 短于这个不单独合成，否则 TTS 会一个字一个字蹦

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_ASR_MODEL = os.environ.get("VOICE_ASR_MODEL", "base")
# say 的默认音色不保证匹配中文。系统里 `say -v '?'` 能看到 zh_CN 的 Tingting；
# 换个语言的助手就换这个默认值，或直接设 VOICE_TTS_VOICE。
DEFAULT_TTS_VOICE = os.environ.get("VOICE_TTS_VOICE", "Tingting")
TTS_RATE_WPM = 200

SYSTEM_PROMPT = """你是一个语音助手，你的回答会被念出来给用户听。

- 用口语说话，两三句就够，不要写列表、标题、代码块、markdown 标记。
- 不要念出括号、星号、URL；数字按口头习惯读。
- 需要实时信息（时间、天气）就用工具查，不要凭记忆编。
- 查不到就直说没查到，不要猜。
"""


# ----------------------------
# 观测
# ----------------------------


@dataclass
class TurnLatency:
    """一轮的延迟账。三个数都相对 turn_complete 计。"""

    turn: int
    question: str
    answer_chars: int
    ttft_ms: int  # 到首个 LLM token
    first_audio_ms: int  # 到第一个出声的片段（垫话也算）
    total_ms: int  # 到本轮说完（被打断则记打断时刻）
    cancelled: bool


@dataclass
class Metrics:
    turns: int = 0
    barge_ins: int = 0
    fillers: int = 0
    weak_turns: int = 0  # 静音够了但分数不够，判定为「还没说完」
    lag_ms: int = 0  # 帧循环落后墙钟多少（健康指标，见 Scheduler.run）
    rows: list[TurnLatency] = field(default_factory=list)

    def report(self) -> None:
        print("-" * 72)
        for row in self.rows:
            mark = "  (被打断)" if row.cancelled else ""
            # 没吐过 token 就别编一个数出来，写「—」比写 235ms 诚实。
            ttft = f"{row.ttft_ms}ms" if row.ttft_ms >= 0 else "—"
            audio = f"{row.first_audio_ms}ms" if row.first_audio_ms >= 0 else "—"
            print(
                f"#{row.turn}  ttft={ttft}  首包音频={audio}  "
                f"整轮={row.total_ms}ms  答{row.answer_chars}字{mark}"
            )
            print(f"      问: {row.question}")
        if not self.rows:
            print("没跑出完整的一轮对话。")
        print("-" * 72)
        print(
            f"轮次 {self.turns}  抢话 {self.barge_ins}  垫话 {self.fillers}  "
            f"未说完 {self.weak_turns}"
        )
        # 帧循环跟不上就等于音频在积压，离线跑看不出来，真麦克风下就是丢帧。
        print(f"帧循环落后墙钟 {self.lag_ms}ms（越大越危险，>1000ms 就快丢帧了）")
        done = [
            row
            for row in self.rows
            if not row.cancelled and row.ttft_ms >= 0 and row.first_audio_ms >= 0
        ]
        if done:
            # 用中位数而不是均值：网络抖一下的长尾会把均值带偏，中位数才接近日常体感。
            ttfts = sorted(row.ttft_ms for row in done)
            audios = sorted(row.first_audio_ms for row in done)
            print(
                f"中位 TTFT {ttfts[len(ttfts) // 2]}ms  "
                f"中位首包音频 {audios[len(audios) // 2]}ms  样本 {len(done)} 轮"
            )


# ----------------------------
# 音频输入
# ----------------------------


def _offer(queue: asyncio.Queue[np.ndarray], block: np.ndarray) -> None:
    """在事件循环线程里投递一块音频，满了就挤掉最旧的一块。"""
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:  # pragma: no cover - full 之后不该空
            pass
    queue.put_nowait(block)


class MicSource:
    """sounddevice 回调 -> asyncio 队列。

    回调跑在 PortAudio 自己的线程里，拿不到事件循环（get_running_loop 在那里会抛），
    所以循环句柄要在 blocks() 里提前存好，投递用 call_soon_threadsafe 转回循环线程。
    这是接真实设备最容易踩的一脚，也是 demo 里 Frame 列表最值钱的那部分。
    """

    def __init__(self) -> None:
        self._stream: Any = None
        self._queue: asyncio.Queue[np.ndarray] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _callback(self, indata: np.ndarray, frames: int, info: Any, status: Any) -> None:
        if status:
            print(f"[mic] {status}", file=sys.stderr)
        loop, queue = self._loop, self._queue
        if loop is None or queue is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(_offer, queue, indata[:, 0].copy())
        except RuntimeError:  # 循环正在关，正常收尾
            pass

    async def blocks(self) -> AsyncIterator[np.ndarray]:
        import sounddevice as sd

        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=MIC_QUEUE_MAX)
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=VAD_BLOCK,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:  # PortAudioError：没授权、没设备
            raise RuntimeError(
                "打不开麦克风。到「系统设置 > 隐私与安全性 > 麦克风」给终端授权，"
                f"或改用 --wav 自检。原始错误：{exc}"
            ) from exc

        try:
            while True:
                yield await self._queue.get()
        finally:
            self._stream.stop()
            self._stream.close()


class WavSource:
    """把 16kHz 单声道 wav 按实时节奏喂进来。

    按实时节奏（不是尽快读完）是为了让抢话和延迟测量和真麦克风同量级。
    """

    def __init__(self, path: Path) -> None:
        with wave.open(str(path), "rb") as handle:
            if handle.getframerate() != SAMPLE_RATE or handle.getnchannels() != 1:
                raise RuntimeError(f"{path} 需要 16kHz 单声道 wav，先用 say 或 ffmpeg 转好。")
            raw = handle.readframes(handle.getnframes())
        self._samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    async def blocks(self) -> AsyncIterator[np.ndarray]:
        for start in range(0, len(self._samples), VAD_BLOCK):
            chunk = self._samples[start : start + VAD_BLOCK]
            if len(chunk) < VAD_BLOCK:
                return
            yield chunk
            await asyncio.sleep(BLOCK_MS / 1000)


# ----------------------------
# VAD / ASR
# ----------------------------


class SileroVad:
    """Silero VAD v5：每块 512 采样给一个「有没有人声」的概率。

    单块推理是毫秒量级，跑在事件循环里可以接受；真生产会把它丢到独立线程/进程，
    让音频采集和模型推理完全解耦。
    """

    def __init__(self) -> None:
        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        self._model = load_silero_vad()

    def is_speech(self, samples: np.ndarray) -> bool:
        # no_grad 不只是习惯：jit 模型的参数带 requires_grad，不关的话每块音频都在
        # 建一张反向图，纯浪费——推理 32ms 一次的东西不该有这部分开销。
        with self._torch.no_grad():
            prob = self._model(self._torch.from_numpy(samples), SAMPLE_RATE)
        return float(prob) >= VAD_THRESHOLD

    def reset(self) -> None:
        """清内部状态。抢话后必须调，否则上一句的上下文会污染下一句的判断。"""
        self._model.reset_states()


class Asr:
    """faster-whisper，CPU int8。见模块 docstring 第 2、3 条。

    每次调用都转写整段缓冲，CPU 推理是阻塞的，所以调用方一律走 asyncio.to_thread——
    丢在事件循环里会连麦克风回调一起卡住。
    """

    def __init__(self, model_name: str) -> None:
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, samples: np.ndarray) -> str:
        # 太短的音频喂给 whisper 只会得到幻觉出来的字（实测过），干脆当没听见。
        # 顺带挡住 partial 和 settle 抢同一段缓冲时的空数组——两个任务只差一次
        # 事件循环就能撞上：settle 清了缓冲，partial 才来取 samples。
        if len(samples) < MIN_UTTERANCE_MS * SAMPLE_RATE // 1000:
            return ""
        segments, _ = self._model.transcribe(
            samples,
            beam_size=1,
            vad_filter=False,  # 切分已经由我们的 VAD 做过了
            condition_on_previous_text=False,
        )
        return "".join(segment.text for segment in segments).strip()


@dataclass
class Utterance:
    """用户这一句攒下来的音频和静音时长。"""

    blocks: list[np.ndarray] = field(default_factory=list)
    silence_ms: int = 0

    def add(self, samples: np.ndarray) -> None:
        self.blocks.append(samples)
        self.silence_ms = 0

    @property
    def duration_ms(self) -> int:
        return len(self.blocks) * BLOCK_MS

    @property
    def samples(self) -> np.ndarray:
        if not self.blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.blocks)

    def clear(self) -> None:
        self.blocks.clear()
        self.silence_ms = 0


# ----------------------------
# TTS
# ----------------------------


class Speaker:
    """把句子交给 TTS，并且能被打断。

    play：say 直接出声。file：合成到 tts_out/ 不出声（无声卡环境）。off：跳过。
    三种模式共用一个进程句柄，所以 stop() 对三者都成立——打断走的是同一条路。
    """

    def __init__(self, mode: str, out_dir: Path) -> None:
        self._mode = mode
        self._out_dir = out_dir
        self._proc: asyncio.subprocess.Process | None = None
        self._index = 0

    def _argv(self, text: str) -> list[str]:
        argv = ["say", "-v", DEFAULT_TTS_VOICE, "-r", str(TTS_RATE_WPM)]
        if self._mode == "file":
            self._out_dir.mkdir(parents=True, exist_ok=True)
            argv += ["-o", str(self._out_dir / f"utt-{self._index:03d}.aiff")]
            self._index += 1
        return argv + [text]

    async def say(self, text: str) -> None:
        if self._mode == "off":
            await asyncio.sleep(len(text) * 0.06)  # 假装念完，保住时序
            return
        self._proc = await asyncio.create_subprocess_exec(
            *self._argv(text),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._proc.wait()
        self._proc = None

    def stop(self) -> None:
        """kill 掉正在出声的进程。这就是抢话的「停声」动作。"""
        proc = self._proc
        if proc is not None and proc.returncode is None:
            proc.terminate()


_SENTENCE_END = re.compile(r"[。！？!?；;…\n]")

# 中文句尾标点。demo 的 SENTENCE_END_CHARS 只有 ".?!"，中文标点落到词数兜底那一路。
_CJK_END_CHARS = "。！？…；"
_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff]")


def turn_score(text: str) -> float:
    """demo 的 turn_completion_score 加一层中文兜底。

    demo 的启发式有两处只认拉丁文，实测都踩到了：
    1. 句尾标点表里没有「？」「。」，ASR 吐出中文问号不算句尾，分数从 0.95 掉到 0.2；
    2. 词数按空白切（len(text.split())），中文整句没有空白，永远切成 1 个词拿最低分，
       于是助手一直等不到「说完了」——中文场景下这是致命的。
    中文按字计数、补上全角标点，阈值表仍旧沿用 demo 的（见 TURN_SCORE_THRESHOLD 说明）。

    这只是把 demo 的启发式补齐，不是变强。真生产换成 turn detector 模型后，
    这个函数连同 demo 的 score 一起删掉。
    """
    if not text:
        return 0.0
    if text.rstrip().endswith(_CJK_END_CHARS):
        return SENTENCE_END_SCORE
    if _CJK_RE.search(text):
        return turn_completion_score(" ".join(text))  # 一字当一词
    return turn_completion_score(text)


class SentenceBuffer:
    """把流式 token 攒成能整句念出去的句子。

    攒句子是必须的：逐 token 送 TTS 会把「你好」念成「你」「好」，韵律全毁。
    所以 LLM 的流式粒度（token）和 TTS 的消费粒度（句子）之间必须有这一层。
    """

    def __init__(self) -> None:
        self._buffer = ""

    def push(self, delta: str) -> list[str]:
        self._buffer += delta
        parts = _SENTENCE_END.split(self._buffer)
        if len(parts) == 1:
            return []
        self._buffer = parts[-1]  # 最后一段还没结束，留到下一轮
        return [p.strip() for p in parts[:-1] if len(p.strip()) >= MIN_SENTENCE_CHARS]

    def flush(self) -> list[str]:
        tail = self._buffer.strip()
        self._buffer = ""
        return [tail] if tail else []


# ----------------------------
# 工具
# ----------------------------


@tool
def get_time(timezone: str) -> str:
    """查某个时区的当前时间。timezone 用 IANA 名字，例如 Asia/Tokyo、Asia/Shanghai。"""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except Exception:
        return f"查不到时区 {timezone}。"
    return now.strftime("%H:%M")


@tool
async def get_weather(city: str) -> str:
    """查某个城市当前的天气。city 用英文名，例如 Tokyo。"""
    params = {"format": "%l: %C %t, 湿度 %h", "m": ""}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(f"https://wttr.in/{city}", params=params)
            response.raise_for_status()
    # 断网抛的是 ConnectError，它是 TransportError 的子类，也继承自 HTTPError；
    # 只接 HTTPStatusError 会把这种情况下漏出去打崩整轮。
    except httpx.HTTPError as exc:
        return f"天气服务没连上（{type(exc).__name__}），没查到。"
    return response.text.strip()


VOICE_TOOLS = [get_time, get_weather]


# ----------------------------
# 一轮对话
# ----------------------------


class TurnRunner:
    """跑一轮「问题 -> 流式回答 -> 出声」，并且允许被从外面掐断。

    两条协程分工，这是生产上最关键的划分：
    - run_turn  拉 LLM 流，攒句子塞队列（IO 密集，要跑满）
    - _player   从队列取句子去念（念是慢的，绝不能挡住拉流）
    合成一条协程的话，「念第一句」和「继续拉 token」会互相阻塞，
    首包音频延迟直接变成「整段回答生成完」的时间。
    """

    def __init__(
        self,
        agent: Any,
        speaker: Speaker,
        metrics: Metrics,
    ) -> None:
        self._agent = agent
        self._speaker = speaker
        self._metrics = metrics
        # 出声那一刻要通知调度器切状态，但调度器要等 TurnRunner 建好才能建，
        # 所以这里先留空，由 bind_first_audio 事后接上。
        self._on_first_audio: Callable[[], None] | None = None
        self.first_audio_ms = -1

    def bind_first_audio(self, callback: Callable[[], None]) -> None:
        self._on_first_audio = callback

    async def run_turn(self, question: str, turn: int) -> None:
        started = time.monotonic()
        self.first_audio_ms = -1
        sentences: asyncio.Queue[str | None] = asyncio.Queue()
        player = asyncio.create_task(self._player(sentences, started))

        answer: list[str] = []
        buffer = SentenceBuffer()
        ttft_ms = -1
        cancelled = False

        try:
            async for message, metadata in self._agent.astream(
                {"messages": [{"role": "user", "content": question}]},
                stream_mode="messages",
            ):
                # 只收 model 节点吐的增量：tools 节点上流的是工具结果，念出来就成复读了。
                if metadata.get("langgraph_node") != "model":
                    continue
                delta = message.content
                if not isinstance(delta, str) or not delta:
                    continue
                if ttft_ms < 0:
                    ttft_ms = int((time.monotonic() - started) * 1000)
                answer.append(delta)
                for sentence in buffer.push(delta):
                    sentences.put_nowait(sentence)
            for sentence in buffer.flush():
                sentences.put_nowait(sentence)
        except asyncio.CancelledError:
            # 抢话走这条路：agent 的 HTTP 流在这里被掐断，连接随之关闭。
            cancelled = True
            raise
        finally:
            sentences.put_nowait(None)  # 通知 player 收工
            if cancelled:
                player.cancel()
            else:
                await player  # 等最后几句念完，否则收尾时会吞掉尾巴
            self._metrics.rows.append(
                TurnLatency(
                    turn=turn,
                    question=question,
                    answer_chars=len("".join(answer)),
                    ttft_ms=ttft_ms,
                    first_audio_ms=self.first_audio_ms,
                    total_ms=int((time.monotonic() - started) * 1000),
                    cancelled=cancelled,
                )
            )

    async def _player(self, queue: asyncio.Queue[str | None], started: float) -> None:
        # 首句迟到就先垫一句：通话里出现一秒以上的死寂，比答得慢更让人以为掉线了。
        # 用「首句就绪」而不是「首 token」做判据，因为用户感知的是声音，不是 token。
        try:
            sentence = await asyncio.wait_for(queue.get(), timeout=FILLER_AFTER_MS / 1000)
        except asyncio.TimeoutError:
            self._metrics.fillers += 1
            await self._emit(FILLER_TEXT, started)
            sentence = await queue.get()

        while sentence is not None:
            await self._emit(sentence, started)
            sentence = await queue.get()

    async def _emit(self, text: str, started: float) -> None:
        if self.first_audio_ms < 0:
            self.first_audio_ms = int((time.monotonic() - started) * 1000)
            if self._on_first_audio is not None:
                self._on_first_audio()
        await self._speaker.say(text)


# ----------------------------
# 调度器
# ----------------------------


class Scheduler:
    """把 VAD 事件、turn 判定、抢话串起来。

    和 demo_main.run_session 是同一个状态机：IDLE -> LISTENING -> WAITING ->
    THINKING -> SPEAKING，TOOL 藏在 agent 内部，不再显式出现（它现在是一次工具调用，
    不是调度器要管的状态）。
    """

    def __init__(
        self,
        vad: SileroVad,
        asr: Asr,
        turn: TurnRunner,
        speaker: Speaker,
        metrics: Metrics,
        *,
        barge_in: bool,
        partials: bool,
    ) -> None:
        self._vad = vad
        self._asr = asr
        self._turn = turn
        self._speaker = speaker
        self._metrics = metrics
        self._barge_in = barge_in
        self._partials = partials

        self._state = "IDLE"
        self._utterance = Utterance()
        self._last_partial_at = -1.0
        self._task: asyncio.Task[None] | None = None
        self._settle_task: asyncio.Task[None] | None = None
        self._partial_task: asyncio.Task[None] | None = None

    async def run(self, source: AsyncIterator[np.ndarray]) -> None:
        """按帧推进。source 是麦克风或 wav，对调度器没有区别。"""
        started = time.monotonic()
        t_ms = 0
        async for samples in source:
            if self._vad.is_speech(samples):
                self._on_speech(samples, t_ms)
            else:
                self._on_silence(t_ms)
            t_ms += BLOCK_MS

            if (
                self._state == "LISTENING"
                and self._utterance.duration_ms >= MAX_UTTERANCE_MS
            ):
                print("[scheduler] 单句超长，强制收尾", file=sys.stderr)
                self._begin_settle(t_ms)

        # 音频源结束了才走到这里。麦克风不会结束，wav 会，而且 wav 常常停在最后一个字上
        # （没有尾部静音），所以补一次判定，免得最后一句被吞掉。
        if self._state == "LISTENING" and self._utterance.blocks:
            self._begin_settle(t_ms)

        # 帧循环的健康指标：t_ms 是音频时间，墙钟是真实时间，两者拉开多少就是积压了多少。
        # 离线放 wav 时它只是个数字，真麦克风下它一旦变大，队列就开始丢帧。
        self._metrics.lag_ms = int((time.monotonic() - started) * 1000) - t_ms

    def _on_speech(self, samples: np.ndarray, t_ms: int) -> None:
        if self._barge_in and self._state in ("THINKING", "SPEAKING") and self._busy:
            # 抢话三步，顺序不能换：先掐声音（人已经开口了，晚一拍就被盖住），
            # 再取消这一轮（关掉还在收的 HTTP 流），最后把当前这块音频并进新一轮。
            self._metrics.barge_ins += 1
            print(f"[{t_ms}ms] 抢话：停声并取消本轮")
            self._speaker.stop()
            self._cancel_turn()
            self._state = "LISTENING"
            self._vad.reset()

        if self._state == "IDLE":
            self._state = "LISTENING"
            self._vad.reset()

        if self._state != "LISTENING":
            return  # THINKING/SPEAKING 且没开抢话：半双工，丢弃输入

        self._utterance.add(samples)
        now = time.monotonic()
        if not self._partials:
            return
        if (
            self._utterance.duration_ms >= MIN_UTTERANCE_MS
            and (now - self._last_partial_at) * 1000 >= ASR_INTERVAL_MS
        ):
            self._last_partial_at = now
            # partial 是尽力而为的：base 模型在 CPU 上转 3 秒音频要 1.2 秒左右
            # （实测 0.4 倍实时），所以上一轮还没转完就直接跳过这一拍，绝不排队。
            # 在这里 await 会把帧循环堵住，麦克风队列随即积压，丢的是真人的话。
            if self._partial_task is None or self._partial_task.done():
                self._partial_task = asyncio.create_task(self._partial(t_ms))

    async def _partial(self, t_ms: int) -> None:
        # partial 目前只用来打印。真生产会把它喂给 turn detector 做语义判定，
        # 而不是干等静音——这就是「说完就答」和「静音才答」的差距。
        partial = await asyncio.to_thread(self._asr.transcribe, self._utterance.samples)
        if partial:
            print(f"[{t_ms}ms] partial: {partial}")

    def _on_silence(self, t_ms: int) -> None:
        if self._state != "LISTENING":
            return
        self._utterance.silence_ms += BLOCK_MS
        if self._utterance.silence_ms < SILENCE_TRIGGER_MS:
            return
        self._begin_settle(t_ms)

    def _begin_settle(self, t_ms: int) -> None:
        """进 WAITING 并起一个判定任务。

        转写和打分是阻塞的，必须离开帧循环——在这里 await 的话，这一两百毫秒里
        麦克风队列会开始积压，延迟就是这么一点点堆出来的。
        """
        self._state = "WAITING"
        self._settle_task = asyncio.create_task(self._settle(t_ms))

    async def _settle(self, t_ms: int) -> None:
        text = await asyncio.to_thread(self._asr.transcribe, self._utterance.samples)
        if self._state != "WAITING":
            return  # 判定期间被抢话或被打断，这次结果作废

        score = turn_score(text)
        if not text or score < TURN_SCORE_THRESHOLD:
            # 分数不够：当作「还没说完」，回 LISTENING 接着攒，别急着抢话。
            # 这就是 demo 里 false_cutoffs 那一支，区别是不丢弃已攒的音频。
            # 静音计数必须清零：不清的话下一帧又满足触发条件，会变成每帧跑一次
            # ASR——CPU 直接烧满，而且结果是同一个。改成每再攒 500ms 重判一次。
            self._metrics.weak_turns += 1
            print(f"[{t_ms}ms] 静音但分数 {score:.2f}，继续等")
            self._utterance.silence_ms = 0
            self._state = "LISTENING"
            return

        print(f"[{t_ms}ms] turn complete score={score:.2f}  问：{text}")
        self._utterance.clear()
        self._last_partial_at = -1.0
        self._metrics.turns += 1
        self._state = "THINKING"
        self._task = asyncio.create_task(self._turn.run_turn(text, self._metrics.turns))
        self._task.add_done_callback(self._on_turn_done)

    def _on_turn_done(self, task: asyncio.Task[None]) -> None:
        if self._state in ("THINKING", "SPEAKING"):
            self._state = "IDLE"
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            print(f"[scheduler] 这一轮失败：{exc!r}", file=sys.stderr)

    def note_first_audio(self) -> None:
        if self._state == "THINKING":
            self._state = "SPEAKING"

    @property
    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def _cancel_turn(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def drain(self) -> None:
        """等手里还没说完的那一轮收尾。

        音频源放完了不等于该走人了：wav 播完时那一轮可能才答到一半，
        直接 shutdown 会把回答连同 TTS 一起掐掉。超时收尾时不调这个。

        必须循环到没有在跑的任务为止，不能只在开头取一次快照：
        turn 任务是 settle 任务在结束前才创建出来的，一次快照只会看到 None，
        接着 shutdown 就把刚建好的那轮干掉——连 finally 都来不及跑，报表是空的。
        """
        while True:
            pending = [
                task
                for task in (self._partial_task, self._settle_task, self._task)
                if task is not None and not task.done()
            ]
            if not pending:
                return
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def shutdown(self) -> None:
        self._cancel_turn()
        for task in (self._settle_task, self._partial_task):
            if task is not None and not task.done():
                task.cancel()
        self._settle_task = None
        self._partial_task = None


# ----------------------------
# 装配
# ----------------------------


def build_agent() -> Any:
    # 思考模式默认开着时多轮工具调用要回传 reasoning_content，而且首 token 会慢很多。
    # 语音场景首 token 最贵，所以关掉。
    model = ChatDeepSeek(
        model=os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL),
        temperature=0,
        max_retries=2,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return create_agent(model=model, tools=VOICE_TOOLS, system_prompt=SYSTEM_PROMPT)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="实时语音助手（生产版）")
    parser.add_argument("--wav", type=Path, help="用 16kHz 单声道 wav 代替麦克风")
    parser.add_argument("--tts", choices=("play", "file", "off"), default="play")
    parser.add_argument("--seconds", type=float, default=0, help="跑这么多秒后收尾，0 表示一直跑")
    parser.add_argument("--no-barge-in", action="store_true", help="半双工：出声时丢弃输入")
    parser.add_argument(
        "--partials",
        action="store_true",
        help="打开重转式 partial（默认关，见模块 docstring 第 2 条）",
    )
    return parser.parse_args()


async def serve(args: argparse.Namespace) -> None:
    metrics = Metrics()
    speaker = Speaker(args.tts, Path(__file__).resolve().parent / "tts_out")
    turn = TurnRunner(build_agent(), speaker, metrics)
    scheduler = Scheduler(
        vad=SileroVad(),
        asr=Asr(DEFAULT_ASR_MODEL),
        turn=turn,
        speaker=speaker,
        metrics=metrics,
        barge_in=not args.no_barge_in,
        partials=args.partials,
    )
    # 出声那一刻要把状态切到 SPEAKING，抢话的分支只看状态和任务是否还活着。
    turn.bind_first_audio(scheduler.note_first_audio)

    if args.wav is not None:
        print(f"[boot] 用 {args.wav} 代替麦克风，实时节奏")
        source = WavSource(args.wav).blocks()
    else:
        source = MicSource().blocks()

    runner = scheduler.run(source)
    timed_out = False
    try:
        if args.seconds > 0:
            await asyncio.wait_for(runner, timeout=args.seconds)
        else:
            await runner
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        if timed_out:
            print(f"[boot] 到 {args.seconds}s，收尾")
        else:
            # 音频放完了，但可能还有一轮在答——等人把话说完再退出。
            await scheduler.drain()
        scheduler.shutdown()
        await asyncio.sleep(0)  # 让取消落地，再打报表
        metrics.report()


def main() -> None:
    args = parse_args()
    # ChatDeepSeek 在构造时就校验密钥，所以必须在建模型之前读进环境。
    load_local_env(Path(__file__).resolve().parent)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        sys.exit("缺少 DEEPSEEK_API_KEY。可写在环境变量或 deskpet/local.env。")
    if args.tts == "play":
        print("[boot] 外放会自激，请戴耳机；不想戴就加 --no-barge-in")

    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        print("\n[boot] 手动停止")
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
