"""Real-time voice pipeline：VAD + turn detection + barge-in 调度。

流式调度器的最小骨架：
1. Frame stream：20ms 一帧的模拟音频，VAD 判有没有人声，ASR 给累积 partial
2. Turn detector：静音攒够了，再用 partial 打个「这句说完了」的分
3. State machine：IDLE -> LISTENING -> WAITING -> THINKING -> SPEAKING，TOOL 走旁路
4. Barge-in：用户在我们说话时又开口，立刻停 TTS、回 LISTENING
5. Metrics：turn complete / 首个 LLM token / 首个音频包 / 端到端延迟

搜「重构：」可以跳到每一处改动。注释写的是「为什么这样改」和「以后怎么接」，
不是复述代码在做什么。
"""

import random
from dataclasses import dataclass, field
from enum import Enum, auto

# ----------------------------
# 时间常量
# ----------------------------

# 重构：原来这些数字散在 synth_call 和 run_session 里，20（帧长）还各写一份。
# 一帧多少毫秒是整条流水线共同的前提；提成模块级常量，以后换采样率只动这里。
FRAME_MS = 20
PREPEND_SILENCE_FRAMES = 6  # 开口前的静音
FRAMES_PER_WORD = 16  # 每个词约 320ms
SUFFIX_SILENCE_FRAMES = 110  # 句尾静音，要盖住 tool + LLM + TTS

SILENCE_TRIGGER_MS = 500  # 静音多久才去问 turn detector
TURN_SCORE_THRESHOLD = 0.6  # 低于这个分就继续等，别急着抢话
LLM_FIRST_TOKEN_MS = 140  # 模拟首 token 延迟
TTS_FIRST_AUDIO_MS = 180  # 模拟 TTS 首包延迟
FILLER_DELAY_MS = 300  # 工具还没回来，先垫一句

# ----------------------------
# Frame stream
# ----------------------------


@dataclass
class Frame:
    """一帧 20ms 的音频。"""

    t_ms: int  # 会话开始以来的时间戳
    is_speech: bool  # VAD 判决（Silero v5 替身）
    partial: str = ""  # ASR 累积 partial（Deepgram Nova-3 替身）


def synth_call(script: str, start_ms: int = 0, noise: float = 0.0) -> list[Frame]:
    """把一句话展开成帧流。noise 是 VAD 误报率，用来试 false cutoff。"""
    words = script.split()
    frames: list[Frame] = []
    t = start_ms

    # 重构：原稿 t 从 0 起，start_ms 收下了却没用——会话 2 要拼接两段音频时
    # 时间戳会重叠。现在 t 从 start_ms 起算。
    for _ in range(PREPEND_SILENCE_FRAMES):
        frames.append(Frame(t_ms=t, is_speech=random.random() < noise))
        t += FRAME_MS

    # 重构：原稿 word 一帧就切走，于是「一句话」总共 20ms，整个调度器的时序
    # 被压缩了 16 倍；turn complete、抢话点全部对不上真实延迟。
    # 每个词铺 FRAMES_PER_WORD 帧，partial 在这段时间里保持不变（真实 ASR 也是这样）。
    partial = ""
    for i, _ in enumerate(words, start=1):
        # 重构：原稿 partial = (partial + " " + word).strip()，每个词重建一次整句；
        # 词数一多就是平方级。join 只拼一次，也没有 strip 带来的首词特判。
        partial = " ".join(words[:i])
        for _ in range(FRAMES_PER_WORD):
            frames.append(Frame(t_ms=t, is_speech=True, partial=partial))
            t += FRAME_MS

    # 重构：原稿尾静音的 is_speech 用 random.random() < noise，和「句尾一定安静」
    # 这个前提矛盾（noise > 0 时会继续触发 speech）。尾静音固定 False。
    for _ in range(SUFFIX_SILENCE_FRAMES):
        frames.append(Frame(t_ms=t, is_speech=False, partial=partial))
        t += FRAME_MS

    return frames


# ----------------------------
# Turn detector
# ----------------------------

# 重构：END_CHARS / BOUNDS 原本是函数体里的局部字面量，每次调用重建一遍。
# 提成模块常量，阈值和分数也才有名字可引用。
SENTENCE_END_CHARS = (".", "?", "!")
SENTENCE_END_SCORE = 0.95
# 词数下界 -> 完成度分：词越少越像还没说完。
PARTIAL_WORD_BOUNDS: tuple[tuple[int, float], ...] = ((3, 0.2), (6, 0.55))
PARTIAL_SCORE_MAX = 0.75  # 词够多但句尾没标点


def turn_completion_score(partial: str) -> float:
    """LiveKit turn-detector 的替身：句尾标点最可信，否则退化成数词。"""
    if not partial:
        return 0.0

    if partial.rstrip().endswith(SENTENCE_END_CHARS):
        return SENTENCE_END_SCORE

    n = len(partial.split())
    # 重构：原稿 for bound, score in BOUNDS: if n < bound: return score，
    # 后面再 return 0.75。next() 把「第一个满足的下界」这个意图直接写出来，
    # 也不会漏掉「所有下界都不满足」的兜底值。
    return next(
        (score for bound, score in PARTIAL_WORD_BOUNDS if n < bound),
        PARTIAL_SCORE_MAX,
    )


# ----------------------------
# State machine
# ----------------------------


class State(Enum):
    """调度器状态。

    重构：原稿 SPEAKING 拼成 SPEEKING。枚举成员名只在日志和调试器里出现，
    拼错不会报错，但你会 grep 不到它，和日志字符串也对不上。
    """

    IDLE = auto()
    LISTENING = auto()  # 用户正在说
    WAITING = auto()  # VAD 说静了，在等 turn score
    THINKING = auto()  # LLM 在流，还没有 TTS
    SPEAKING = auto()  # TTS 在出音频
    TOOL = auto()  # 旁路工具在飞


@dataclass
class Metrics:
    """一次 session 的观测结果。"""

    # 重构：原稿 events : list[str] 冒号前多一个空格（PEP 8 是 events: list[str]），
    # log 又漏了返回类型。不影响运行，但和文件里其它标注不一致。
    events: list[str] = field(default_factory=list)
    turn_complete_ms: int = 0
    first_llm_token_ms: int = 0
    first_audio_out_ms: int = 0
    false_cutoffs: int = 0
    barge_ins: int = 0

    def log(self, event: str) -> None:
        self.events.append(event)

    def latency_ms(self) -> int:
        """turn complete 到第一包音频的延迟；还没出声返回 -1。

        重构：-1 是「没测到」的哨兵，不是延迟 -1ms。接监控时该换成 None，
        把「没测到」和「测到 0」分开；现在先保持原样，别让 main 的格式化跟着改。
        """
        if self.turn_complete_ms and self.first_audio_out_ms:
            return self.first_audio_out_ms - self.turn_complete_ms
        return -1


# ----------------------------
# Tool side channel
# ----------------------------


@dataclass
class Tool:
    name: str
    latency_ms: int
    result: str


WEATHER = Tool("weather.tokyo_tomorrow", latency_ms=420, result="68/52 partly cloudy")


# ----------------------------
# Scheduler
# ----------------------------


def should_barge_in(f: Frame, state: State, barge_in_at_ms: int | None) -> bool:
    """用户在我们 THINKING / SPEAKING 时又开口 = 抢话。

    重构：原稿四个条件（时间戳、两个状态、is_speech）挤在一个 if 里，读的人要数括号；
    而且写的是 `if barge_in_at_ms and ...`——0 是合法时间戳，布尔语境里却是假，
    barge_in_at_ms=0 的会话永远不触发抢话。判断「有没有给」要用 is not None。
    """
    return (
        barge_in_at_ms is not None
        and f.t_ms >= barge_in_at_ms
        and state in (State.THINKING, State.SPEAKING)
        and f.is_speech
    )


def run_session(
    frames: list[Frame],
    use_tool: bool = True,
    barge_in_at_ms: int | None = None,
) -> Metrics:
    """按帧推进整条流水线，返回这次 session 的观测。"""
    m = Metrics()

    state = State.IDLE
    silence_run_ms = 0
    final_partial = ""
    # 重构：原稿用 -1 表示「定时器还没设」，再写 `> 0` 判断。可 f.t_ms + 140 恒正，
    # 这个判断其实从来没拦住过什么，三个哨兵值还各有一套比较。统一用 None +
    # `is not None`，「没开始」和「时间戳刚好是 0」不再纠缠。
    llm_ready_at: int | None = None  # 模拟首 token 到点时刻
    tts_ready_at: int | None = None  # 模拟首包音频到点时刻
    tool_start_at: int | None = None
    filler_emitted = False

    for f in frames:
        if should_barge_in(f, state, barge_in_at_ms):
            m.barge_ins += 1
            m.log(f"{f.t_ms}ms Barge-in, cancelling TTS re-arm ASR")
            state = State.LISTENING
            # 重构：原稿只重置了两个「已开始」标志，没清 final_partial 和
            # silence_run_ms。抢话之后是新的一轮，静音计数必须从零起，
            # 否则前一轮攒的静音会把新一轮的 turn complete 提前。
            silence_run_ms = 0
            tts_ready_at = None
            llm_ready_at = None
            continue

        if state == State.IDLE:
            if f.is_speech:
                state = State.LISTENING
                m.log(f"{f.t_ms}ms Speech detected, entering LISTENING")

        elif state == State.LISTENING:
            if f.is_speech:
                silence_run_ms = 0
                final_partial = f.partial or final_partial
            else:
                silence_run_ms += FRAME_MS
                if silence_run_ms >= SILENCE_TRIGGER_MS:
                    score = turn_completion_score(final_partial)
                    if score >= TURN_SCORE_THRESHOLD:
                        state = State.WAITING
                        m.turn_complete_ms = f.t_ms
                        m.log(
                            f"{f.t_ms}ms Turn complete, score: {score:.2f}, "
                            f"partial: {final_partial}"
                        )
                    else:
                        m.log(f"{f.t_ms}ms SILENCE but score: {score:.2f}, waiting")

        # 重构：这一段必须是顶层 if，不能缩进到上面的 elif LISTENING 里面。
        # 同一帧里刚判定成 WAITING，就要在这一帧把 LLM 打出去；缩进进去的话
        # 状态变了却没人处理，而且 TOOL / THINKING / SPEAKING 永远不会被访问到，
        # first_llm_token_ms 和 first_audio_out_ms 会一直是 0。
        if state == State.WAITING:
            llm_ready_at = f.t_ms + LLM_FIRST_TOKEN_MS
            state = State.THINKING
            m.log(f"{f.t_ms}ms LLM call fired")

            if use_tool:
                # 重构：原稿先设 THINKING 再设 TOOL，THINKING 那一行等于白写。
                # 有工具就直接进 TOOL，省掉一次无意义的状态赋值。
                tool_start_at = f.t_ms
                state = State.TOOL

        elif state == State.TOOL:
            if tool_start_at is not None and not filler_emitted:
                if f.t_ms - tool_start_at >= FILLER_DELAY_MS:
                    filler_emitted = True
                    m.log(f"{f.t_ms}ms filler 'one second, let me check'")

            if (
                tool_start_at is not None
                and f.t_ms - tool_start_at >= WEATHER.latency_ms
            ):
                # 重构：原稿把完成时刻记进 tool_done_at，但全文没人读它。
                # 只为观测的字段要进 Metrics，不该留一个只赋值不读的局部变量。
                m.log(f"{f.t_ms}ms tool call complete, result: {WEATHER.result}")
                llm_ready_at = f.t_ms + LLM_FIRST_TOKEN_MS
                state = State.THINKING

        elif state == State.THINKING:
            if llm_ready_at is not None and f.t_ms >= llm_ready_at:
                if m.first_llm_token_ms == 0:
                    m.first_llm_token_ms = f.t_ms
                    m.log(f"{f.t_ms}ms first LLM token received")
                tts_ready_at = f.t_ms + TTS_FIRST_AUDIO_MS
                state = State.SPEAKING

        elif state == State.SPEAKING:
            if tts_ready_at is not None and f.t_ms >= tts_ready_at:
                if m.first_audio_out_ms == 0:
                    m.first_audio_out_ms = f.t_ms
                    m.log(f"{f.t_ms}ms first audio token received")

    return m


# ----------------------------
# Demo
# ----------------------------

# 抢话的注入点：尾静音里从倒数第 BARGE_IN_LEAD_FRAMES 帧起改 BARGE_IN_COUNT 帧。
# 重构：原稿 `idx = len(frames) - 20 + i` 配 `if 0 <= idx < len(frames)`——
# i < 8 < 20，边界检查恒真，读的人却要先验算一遍。
BARGE_IN_LEAD_FRAMES = 20
BARGE_IN_COUNT = 8
BARGE_IN_LEAD_MS = 60  # 判定时刻比第一帧语音早一点，保证能触发


def arm_barge_in(frames: list[Frame]) -> int:
    """把尾部几帧改成语音来模拟抢话，返回抢话判定时刻。

    重构：原稿在 main 里就地改 frames，还返回不了时刻，调用方要再算一次
    frames[-20].t_ms - 60。把「改哪几帧」和「什么时候算抢话」绑在一个函数里，
    main 就只剩一句调用。
    """
    start = len(frames) - BARGE_IN_LEAD_FRAMES
    for frame in frames[start : start + BARGE_IN_COUNT]:
        frame.is_speech = True
    return frames[start].t_ms - BARGE_IN_LEAD_MS


def report(m: Metrics, *, timeline: bool = True) -> None:
    """打印事件流；timeline=True 时再补三个时间点。

    重构：原来这段事件循环在 main 里抄了两遍，session 2 还少打几行。
    timeline 开关只是把「两个 session 原本打印不一样」这件事显式写出来，
    输出保持原样。
    """
    for line in m.events:
        print(" ", line)
    if not timeline:
        return
    print(f"  turn_complete  @ {m.turn_complete_ms}ms")
    print(f"  first_llm_tok  @ {m.first_llm_token_ms}ms")
    print(f"  first_audio_out @ {m.first_audio_out_ms}ms")


def main() -> None:
    # 固定 VAD 误报序列，两次运行输出一致，也方便写断言。
    random.seed(0)

    print("=== session 1: clean call with tool (weather) ===")
    frames = synth_call("what is the weather in tokyo tomorrow")
    m = run_session(frames, use_tool=True)
    report(m)
    print(f"  turn latency   = {m.latency_ms()}ms")

    print()
    print("=== session 2: user barges in mid-response ===")
    frames = synth_call("tell me a long story about")
    m = run_session(frames, use_tool=False, barge_in_at_ms=arm_barge_in(frames))
    report(m, timeline=False)
    print(f"  barge_ins = {m.barge_ins}")


if __name__ == "__main__":
    main()
