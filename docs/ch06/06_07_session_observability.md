# 6.7 回看：会话的可观测雏形

## 6.7.1 先问一个具体问题

日志存在磁盘上了，但存着不等于可看。真正的需求是这样一句话：

> 上周那个把重试次数从 0 改成 3 的任务，它当时到底怎么做的？中间失败过吗？

这个问题用 6.1 的 JSONL 能回答——**但你得手动打开那个文件，在一堆 `{"seq":...}` 里翻。** 那不算「能回看」。

「能回看」的及格线是：**把一条日志还原成一段人能读的东西。** 这一节做一个最小版本。

## 6.7.2 一个回看脚本

```python
# harnex/session/replay.py —— 把一条 JSONL 会话还原成人能读的轨迹
import json
import sys
import time
from pathlib import Path

LOG_DIR = Path("sessions")


def render(session_id: str) -> str:
    path = LOG_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return f"没有找到会话 {session_id}"
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        e = json.loads(raw)
        when = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
        kind = e["kind"]
        if kind == "user_message":
            lines.append(f"[{when}] 用户：{e['content']}")
        elif kind == "assistant_message":
            text = (e["message"].get("content") or "").strip()
            if text:
                lines.append(f"[{when}] Harnex：{text}")
            for call in e["message"].get("tool_calls") or []:
                fn = call["function"]
                lines.append(f"[{when}]   → 调用 {fn['name']} {fn['arguments']}")
        elif kind == "tool_result":
            head = e["content"].strip().replace("\n", " ")[:60]
            lines.append(f"[{when}]   ← {e['name']} 返回：{head}…")
        elif kind == "compaction":
            lines.append(f"[{when}]   ◆ 发生了一次压缩")
    return "\n".join(lines)


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "latest"
    if sid == "latest":
        files = sorted(LOG_DIR.glob("*.jsonl"))
        sid = files[-1].stem if files else ""
    print(render(sid))
```

跑一下：

```text
$ python -m harnex.session.replay latest

[19:17:02] 用户：把 src/uploader.py 里的重试次数从 0 改成 3，然后跑一下测试
[19:17:03] Harnex：我先读一下文件。
[19:17:03]   → 调用 fs_read {"path": "src/uploader.py"}
[19:17:03]   ← fs_read 返回：1  import time 2  import json 3  …
[19:17:04]   → 调用 apply_patch {"path": "src/uploader.py", "old": "retries = 0", …}
[19:17:04]   ← apply_patch 返回：错误：要替换的原文出现 2 次，无法定位
[19:17:05]   → 调用 apply_patch {"path": "src/uploader.py", "old": "    self.retries = 0\n…", …}
[19:17:05]   ← apply_patch 返回：已修改 src/uploader.py（3 行 → 3 行）
[19:17:06]   → 调用 shell {"command": "pytest -q"}
[19:17:09]   ← shell 返回：5 passed in 0.4s
[19:17:10] Harnex：重试次数已改成 3，5 个测试全过。
```

十来行输出，把那次任务从头到尾摊平了。**这就是「能回看」的最低标准**：不用打开原始 JSON，也能回答「它做了什么、按什么顺序、哪一步慢、有没有失败」。

## 6.7.3 为什么要能回看

这个脚本简陋，只有三十来行，但它是后面两章的地基。

**它是第 12 章 trace 看板的用户侧版本。** 第 12 章会把同样的数据画开：每轮耗时、工具调用次数、token 消耗、失败率。这里只是把事件连成一串文字，那里会把它画成图。**数据源是同一份 `sessions/*.jsonl`**——你在这一章写进日志的东西，决定了第 12 章能画出什么。日志里没有的信息，看板再漂亮也变不出来。

**它也是第 20 章「查看任务」的数据来源。** 手机上点开一个历史任务、看它做了什么——底层调用的就是这样的读取逻辑，只是换了个界面。

还有一层更长远的价值：**这份轨迹是你排查「Agent 为什么不听话」的唯一现场。** 模型的行为不可复现，但它的**输入**可以完整复现——日志记下的就是它每一轮看到的全部内容。当它做了一个荒唐的决定，你能回到当时那一刻，看它究竟看到了什么、缺了什么。这是「模型可见即已记录」这条不变式真正兑现价值的地方。

## 6.7.4 一条轨迹看什么

回看不是从头读到尾。有四个地方值得先扫一眼：

- **工具调用的失败**——`tool_result` 里带「错误」的那几条，往往就是任务绕弯的起点
- **压缩发生在哪一轮**——压缩前后的回答质量对比，能暴露压缩策略的毛病（6.4 节）
- **哪一步特别慢**——相邻事件的 `ts` 之差，就是那一轮的耗时
- **用户的打断**——`user_interrupt` 出现在哪，通常意味着模型的判断和你的预期分了岔

这四条都不需要额外信息，它们就藏在 `seq` 和 `ts` 两个字段里。**一份好的日志，是让这些问题各用一行输出就能回答。**

## 6.7.5 一次看一批会话

上面这个脚本一次只渲染一条会话。真实使用里，下一个需求很快就来：

> 这周有哪几次任务中途失败过？

这不是「看一条」能回答的，它要的是在**一批**轨迹上做筛选。不用换工具，还是同一份 JSONL，只是换个读法——**先扫出所有会话的摘要，再挑出你要看的那些。**

```python
# harnex/session/replay.py 追加 —— 列出所有会话的一行摘要
def overview() -> str:
    rows = []
    for path in sorted(LOG_DIR.glob("*.jsonl")):
        text = path.read_text(encoding="utf-8")
        events = [json.loads(line) for line in text.splitlines() if line.strip()]
        kinds = [e["kind"] for e in events]
        tools = kinds.count("tool_result")
        rows.append(f"{path.stem}  事件 {len(events):3d}  工具调用 {tools:2d}  "
                    f"压缩 {kinds.count('compaction')} 次")
    return "\n".join(rows) or "还没有任何会话记录"
```

输出是一张清单：

```text
20261011-091500  事件  42  工具调用  9  压缩 0 次
20261011-140233  事件 128  工具调用 31  压缩 1 次
20261011-173010  事件  17  工具调用  3  压缩 0 次
```

有了这一层，你可以在几秒钟内定位到「那个跑了 128 个事件的会话」。**筛选靠的是结构，不是肉眼**——这也正是 6.1 要把「事件类型」和「时间」固定成两个必填字段的原因：它们是之后所有查询的索引。

三个层次连起来看，会话可观测的路线就很清楚了：

| 层次 | 做什么 | 在哪 |
| --- | --- | --- |
| 看一条 | 渲染单次轨迹 | 本节 `render()` |
| 筛一批 | 按时间、工具、压缩筛会话 | 本节 `overview()` |
| 看趋势 | 耗时、失败率、token 曲线 | 第 12 章 trace 看板 |

本章只到第二层，而且刻意停在命令行。**第三层的图表很好看，但没有前两层的数据结构撑着，它只是把一堆噪声画得更漂亮。**

## 本章收束

到这一章，Harnex 有了记忆：

- **会话日志**——append-only 的事件流，是真相源，可回放、可恢复
- **投影与压缩**——日志投影成消息，预算表量着，压缩按需回收，压缩不动日志
- **长期记忆**——按 key 更新、带来源与置信度，跨会话生效
- **检索**——按相关性取，而不是全量注入
- **回看**——把轨迹还原成人能读的东西

一句话概括这一章：**它从「每次都是初次见面」，变成了「一次比一次更懂你」。**

但有个能力，它一直只在演示里用过：`shell`。5.5 节讲技能包里的脚本时说过它是第 7 章的主角；本章从 6.1 到 6.7 的每一次演示，Harnex 都在调 `shell(command=...)` 跑测试——**而它到现在其实还不会执行命令。** 它能读文件、写文件，却没法真正让任何东西跑起来。

下一章补上这一点。**让它动手。**
