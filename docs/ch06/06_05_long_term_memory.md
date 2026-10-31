# 6.5 长期记忆：跨会话记住「你」

## 6.5.1 三种记忆

「记住用户」这句话太笼统，先把它拆成三类——它们的写入方式和读取方式都不同。

| 类型 | 存什么 | 例子 | 有效期 |
| --- | --- | --- | --- |
| 画像 | 关于用户的稳定事实 | 「用 Python」「团队用 Conventional Commits」 | 长期，直到被纠正 |
| 事件 | 发生过的事 | 「上周重构了 parser」「10 月 3 日修了登录 bug」 | 中期，可过期 |
| 程序性 | 怎么服务这个人 | 「他喜欢先给结论、后给理由」 | 长期 |

三者里最容易被混在一起的是「画像」和「事件」。**画像回答「你是谁」，事件回答「你做过什么」。** 前者几乎不变，后者天天在变。

混存一处的后果是具体的：一句「今天在改登录」被存进画像后，会永远赖在那里，某天你问一个完全无关的问题，它突然冒出来干扰决策——因为系统以为「改登录」是你的一部分特征，而不是一件已经过去的事。

分开存还有第二个好处：**它们的清理策略本来就该不同。** 事件可以按时间过期，画像不行；画像的一条要慎重写入，事件可以随手记。

## 6.5.2 什么时候写入

写入时机有两种，可靠性和代价完全不同。

**显式写入**：用户直接说「记住，我们项目用 pytest」。

- 可靠——这是用户的明确意图
- 但要用户开口，覆盖率低

**隐式写入**：harness 从对话里推断「用户偏好 pytest」。

- 覆盖面广——用户不必刻意说
- 但会猜错，必须带置信度

实践中是 **两者都要，但分开存**：显式写入的置信度给满，隐式推断的给一个中等值，并在被反复印证后上调。分开存还有一个直接的好处：**清理时可以按来源批量处理**——「所有我猜出来的、从没被验证过的记忆，过期就删」。

一条实用的纪律：**隐式写入宁缺毋滥。** 猜错一条记忆的代价，比少记一条大得多——因为它会在未来每一轮都参与决策，还可能顶掉正确的信息。

## 6.5.3 一条记忆里有什么

别把记忆存成裸字符串。至少要有这几个字段：

| 字段 | 作用 |
| --- | --- |
| `key` | 唯一标识，用于 **更新而非新增** |
| `content` | 内容本身 |
| `kind` | 画像 / 事件 / 程序性 |
| `source` | 从哪来的（哪次会话、显式还是推断） |
| `created_at` | 何时写入 |
| `confidence` | 置信度，0–1 |
| `expires_at` | 过期时间，可选 |

其中两个字段最容易被省掉，恰恰最关键。

**`source`（来源）。** 当一条记忆出了问题，你需要能回答「它是谁、在哪、怎么进来的」。没有来源，一条错记忆就无从追溯——你甚至不知道它是自己猜的，还是用户说的。

**`confidence`（置信度）。** 它不是给模型看的，是给**排序和淘汰**用的：置信度低的排到后面，低到一定程度、又很久没被更新过的，就删掉。

## 6.5.4 重复了就更新旧的

长期记忆里最容易坏的地方，是 **同一件事记了两条矛盾的**。

用户三个月前说「我们用 unittest」，上周改口「我们迁到 pytest 了」。如果两次都当新记忆存下来，你的库里就同时躺着「用 unittest」和「用 pytest」——**检索时挑中哪条，纯看运气。**

规矩很简单：**按 `key` 更新，不按内容新增。**

```text
旧:  key=test_framework   content="unittest"
用户: 我们现在改用 pytest 了
新:  key=test_framework   content="pytest"   source="用户纠正"   confidence=1.0
```

有了 `key`，第二条会**覆盖**第一条，而不是并存。用户的一次纠正，就把旧记忆终结了。

这里有个细节值得注意：**用户的纠正属于「显式写入」，置信度直接给满，并且优先级高于任何推断。** 一个从对话里猜出来的「他好像喜欢 unittest」，绝不能压过用户白纸黑字的「我们改用 pytest 了」。

## 6.5.5 按 `key` 存放

```python
# harnex/memory/store.py —— 长期记忆：按 key 更新，条目带来源与置信度
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

MEM_PATH = Path("memory.jsonl")


@dataclass
class MemoryItem:
    key: str
    content: str
    kind: str                      # profile / event / procedure
    source: str                    # 哪次会话、显式还是推断
    created_at: float
    confidence: float = 1.0
    expires_at: float | None = None


class MemoryStore:
    def __init__(self):
        self.items: dict[str, MemoryItem] = {}

    def load(self) -> None:
        if not MEM_PATH.exists():
            return
        for line in MEM_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = MemoryItem(**json.loads(line))
                self.items[item.key] = item

    def remember(self, key: str, content: str, kind: str, source: str,
                 confidence: float = 1.0,
                 expires_at: float | None = None) -> None:
        """写入或更新。同一个 key 只留最新一条——用户纠正会覆盖旧记忆。"""
        item = MemoryItem(key=key, content=content, kind=kind,
                          source=source, created_at=time.time(),
                          confidence=confidence, expires_at=expires_at)
        self.items[key] = item
        with MEM_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    def active(self, now: float | None = None) -> list[MemoryItem]:
        now = now or time.time()
        return [it for it in self.items.values()
                if it.expires_at is None or it.expires_at > now]
```

注意 `load()` 用的是 **后写覆盖**：把 JSONL 顺序读完，后一条同 `key` 的覆盖前一条——**所以磁盘上是追加历史，内存里是当前最新状态**。这又是「记录 vs 状态」的一次应用：磁盘留全，内存只留有效的。

`remember()` 也是同样的双写：内存里按 key 覆盖（保证读到的是最新），磁盘上追加一行（留下变更轨迹）。哪天你想知道「这条记忆被改过几次、什么时候改的」，磁盘上的历史还都在。

顺带说一下 `expires_at`：默认 `None`，意思是永不过期。想让「这周在做登录重构」这种事件记忆自己退场，就传一个时间戳进去，`active()` 会把它滤掉——动手任务 4 用的就是这一手。

## 6.5.6 记住之后怎么用

到这一步，Harnex 能存记忆了。但存进去不算数——**它得在合适的时候真的被用上。**

如果每次对话都把 200 条记忆全塞进系统提示，你就又回到了 6.2 那个预算问题：每轮白烧 5000 token，还把真正相关的那几条淹在无关信息里。下一节解决这件事。
