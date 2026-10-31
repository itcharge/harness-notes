# 6.4 压缩（二）：三类策略与不可逆性

## 6.4.1 三种压缩办法

压缩的具体手段就三类，各有明确的适用边界。

| 策略 | 怎么做 | 适合 | 代价 |
| --- | --- | --- | --- |
| 滑动窗口裁剪 | 只留最近 N 条消息 | 短任务、最近的上下文最重要 | 早期约束可能被裁掉 |
| 摘要压缩 | 让模型把老消息总结成一段 | 长任务、过程冗长 | 一次额外模型调用，可能丢细节 |
| 工具结果瘦身 | 大输出只留用过的部分 | 明显「一大块返回、只用一行」的场景 | 需要判断「哪部分有用」 |

**滑动窗口裁剪** 最便宜：数够 N 条就砍掉最早的。它的问题也很直白——**它按时间砍，不按重要性砍**。用户第 3 轮说的那条约束，和第 28 轮的一句「好的」待遇完全一样。

**摘要压缩** 最聪明也最贵：让模型读一遍要丢掉的消息，写一段摘要保留下来。它好就好在能保住 **语义**，而不只是 **最近**。但有两个风险：摘要本身会失真（模型可能漏掉你觉得重要的那句话），而且它是一次额外的模型调用——你为了省 token，先花了一次 token。

**工具结果瘦身** 最容易被低估。它的场景特别明确：**一个工具返回 50 行，模型只用其中 1 行。** 比如 `ls -la` 返回 80 行，模型看完只得出「有 `src/` 和 `tests/` 两个目录」——那 80 行留在历史里，全是废纸。

## 6.4.2 三种办法排成一条流水线

实践里不是三选一，而是 **排队**，按「先便宜后昂贵」：

1. **先瘦身**——不用模型，效果立竿见影，大输出通常占历史的一半以上
2. **再分堆**——最近的一段原样留下；更老的分两堆，确认没用的直接丢，还有语义价值的留给摘要
3. **最后摘要**——只对第 2 步留下的那一堆动用模型

顺序背后是一条原则：**能用结构性手段解决的，不要用模型手段。** 剪掉一段已知没用的输出，不需要模型判断；一旦让模型总结，成本和不确定性都跟着来，所以排最后。

那滑动窗口呢？它在这条流水线里退到兜底的位置：连摘要都来不及做，或者这条链路压根不允许额外调用模型时，直接砍到最近 N 条，至少保证不超预算。便宜、粗暴、不会崩。

## 6.4.3 压的是展示，日志还在

这是本节最重要的一条，也是 6.1 节两条不变式的直接推论：

> **压缩只能删投影里的消息，绝不能删日志里的事件。**

对比一下 6.1 的 `SessionLog` 和这里的 `messages`：

- `messages` 是**投影**——它随时可以被重新生成、被裁剪、被摘要；它是「当前这一轮要发给模型的东西」
- `SessionLog` 是**记录**——append-only 的；压缩发生时它只多一条 `compaction` 事件，原有事件一条不动

```text
日志（只增）          sessions/xxx.jsonl   ← 完整轨迹，永久保留
  │
  ├─ 投影 A           第 1 轮发出的消息（全量）
  ├─ 投影 B           第 12 轮发出的消息（压缩后）
  └─ 投影 C           第 30 轮发出的消息（再压缩后）
```

**有了这条边界，压缩才敢做。** 任何一次压缩造成的损失，都能从日志里重新投影回来——你可以在第 40 轮时回头翻第 1 轮的原始记录，检查当时到底说了什么。压缩不再是一次「烧掉证据」的操作，而是一次「换个角度看同一份记录」。

反过来，如果压缩直接改日志，那就真不可逆了：**哪天你发现删错了，没有任何东西能还回来。**

## 6.4.4 写成一个函数

```python
# harnex/context/compact.py —— 压缩：先瘦身工具结果，再裁窗口，最后才摘要
def shrink_tool_results(events: list[dict], keep_chars: int = 400) -> list[dict]:
    """工具结果超长时只留开头一段——完整内容仍在日志里。"""
    out = []
    for e in events:
        if e["kind"] == "tool_result" and len(e["content"]) > keep_chars:
            e = {**e, "content": e["content"][:keep_chars] + "\n…（已截断，完整内容见日志）"}
        out.append(e)
    return out


def window(events: list[dict], keep: int = 30) -> list[dict]:
    """滑动窗口：保留最近 keep 条事件。"""
    return events[-keep:]


def _event_text(e: dict) -> str:
    """把一条事件还原成一行文本——助手发言藏在 message 里，要单独取。"""
    if e["kind"] == "assistant_message":
        msg = e["message"]
        parts = [msg.get("content") or ""]
        for call in msg.get("tool_calls") or []:
            fn = call["function"]
            parts.append(f"(调用 {fn['name']} {fn['arguments']})")
        return " ".join(p for p in parts if p)
    return e.get("content", "")


def summarize(old_events: list[dict], chat_fn) -> str:
    """把要丢弃的事件交给模型摘成一段。"""
    text = "\n".join(f"[{e['kind']}] {_event_text(e)}" for e in old_events)
    prompt = ("下面是一段 Agent 与用户的对话记录。请压缩成不超过 150 字的摘要，"
              "保留：任务目标、用户给的约束与纠正、未完成的事项、关键事实"
              "（路径、ID、结论）。丢掉：过程细节、重复内容。\n\n" + text)
    return chat_fn([{"role": "user", "content": prompt}]).content


def compact(events: list[dict], chat_fn, keep_recent: int = 24) -> list[dict]:
    """压缩 = 瘦身 → 摘要老段 → 拼上最近段。返回新投影，不动原日志。"""
    slim = shrink_tool_results(events)
    if len(slim) <= keep_recent:
        return slim
    old, recent = slim[:-keep_recent], window(slim, keep_recent)
    digest = summarize(old, chat_fn)
    return [{"kind": "compaction", "summary": digest}] + recent


def project(events: list[dict]) -> list[dict]:
    """和 6.1 的 project 相比，多认一种事件：压缩摘要。"""
    messages = []
    for e in events:
        if e["kind"] == "compaction":
            messages.append({"role": "system",
                             "content": "以下是对之前对话的摘要：\n" + e["summary"]})
        elif e["kind"] == "user_message":
            messages.append({"role": "user", "content": e["content"]})
        elif e["kind"] == "assistant_message":
            messages.append(e["message"])
        elif e["kind"] == "tool_result":
            messages.append({"role": "tool", "tool_call_id": e["tool_call_id"],
                             "content": e["content"]})
    return messages
```

三处要点：

- **`compact()` 返回新列表，不改入参。** 原事件流纹丝不动——这就是「压缩不动日志」的代码化。
- **`summarize()` 明确告诉模型保留什么、丢什么。** 只写「总结一下」会让模型按它自己的标准取舍，而它的标准和你不同。**压缩的 prompt 是一份需求文档。**
- **`shrink_tool_results()` 先动手。** 它在没有模型参与的情况下就能砍掉最多的一批内容，留到最后的才是摘要。

有两处容易读错，先说明：

- **`window()` 划的是「保留区」，不是「丢弃区」。** 最近 24 条原样留下，更早的整段交给摘要——6.4.2 第 2 步里「原样留下」和「留给摘要」这两件事，都落在这一行上。至于哪几条可以「连摘要都不用、直接丢」，本章不给自动规则：那要人判断，或者事后回看（6.7 节）再决定。
- **`shrink_tool_results()` 偷了个懒：直接留前 400 字。** 真正的「只留用过的部分」得知道模型用了哪几行，那要么让工具返回时就带上行号，要么压缩时让模型自己指认。这版先保证「不爆」，精确度留给后面。

还有一个细节：`project()` 把压缩摘要放进 `role: system`。这不是唯一选法（放进一条 `user` 消息也常见），但 `system` 能明确告诉模型「这是背景，不是新指令」，减少它把摘要当成用户新要求去执行的风险。

## 6.4.5 用 50 轮对话试一次

用一个真实的长会话跑一遍，数字大致是这样：

| 指标 | 压缩前 | 压缩后 |
| --- | --- | --- |
| 轨迹投影 token | 38 600 | 9 200 |
| 其中工具结果 | 26 100 | 3 100 |
| 总占用 | 41 200 / 128k | 11 800 / 128k |

压缩比约 4.2 倍。最值得看的是第二行：**工具结果占了压缩前轨迹投影的近七成**——这就解释了为什么「先瘦身」排在最前面：它一个人就回收了大半空间。

质量的对照也得补一句：压缩完接着问「我们最开始定的那个约束是什么」，它答得上来。**好的压缩，是让模型忘掉过程、记住结论。**

## 收束

到这里，同一场对话内的记忆就算管住了：有日志兜底、有预算表量着、有压缩按需回收。但还剩一件事没解决——**跨对话的记忆**。上面所有手段都只在一次会话内生效，换个会话，一切归零。下一节处理它。
