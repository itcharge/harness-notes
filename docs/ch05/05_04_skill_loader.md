# 5.4 给 Harnex 装上技能包加载器

## 5.4.1 加载器做三件事

回顾 5.3 节那三层。第 1 层是「启动时扫出所有技能包的 `name` 与 `description`」，第 2 层是「匹配后才把正文读进来」。加载器要负责的是第 1 层，以及把第 2 层的入口交给模型。

具体三件事：

1. **扫描**：找到技能目录下所有 `*/SKILL.md`
2. **解析**：只取 frontmatter，正文一个字不读
3. **生成清单**：拼出一段可以放进系统提示的文本

```python
# harnex/skills/loader.py —— 技能包加载器：扫描目录，只把清单交给系统提示
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path("skills")


@dataclass
class SkillPack:
    """技能包的元信息。正文不在这里——它留在磁盘上，等被需要时再读。"""
    name: str
    description: str
    path: Path


def _parse_frontmatter(text: str) -> dict:
    """取出 SKILL.md 头部两行 --- 之间的键值对。不处理嵌套结构。"""
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    meta = {}
    for line in block.splitlines():
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta


class SkillPackLoader:
    """启动时扫描技能目录，把「名字 + 描述 + 正文路径」做成一段清单。"""

    def __init__(self, root: Path = SKILLS_DIR):
        self.root = root
        self.packs: dict[str, SkillPack] = {}

    def discover(self) -> None:
        """只读 frontmatter，不读正文——启动开销与正文长度无关。"""
        for skill_md in sorted(self.root.glob("*/SKILL.md")):
            meta = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            name = meta.get("name") or skill_md.parent.name
            if name != skill_md.parent.name:
                print(f"跳过 {skill_md.parent.name}：name 与目录名不一致")
                continue
            self.packs[name] = SkillPack(
                name=name,
                description=meta.get("description", ""),
                path=skill_md,
            )

    def catalog(self) -> str:
        """清单文本。它常驻系统提示，所以一个字段都不许多写。"""
        if not self.packs:
            return ""
        lines = ["你可以使用下面这些技能包。任务与某个描述匹配时，",
                 "先用 fs_read 读取它的 SKILL.md，再按里面的步骤执行。", ""]
        for pack in self.packs.values():
            lines.append(f"- {pack.name}：{pack.description}")
            lines.append(f"  正文路径：{pack.path}")
        return "\n".join(lines)
```

三个细节：

- **`line.startswith((" ", "\t"))` 跳过缩进行。** 这是为了躲开 `metadata:` 下面的嵌套键（`author`、`version`），它们比顶层字段多缩进两格。这个解析器只认顶层平铺字段——够用，而且六十行里能讲完。
- **`name != skill_md.parent.name` 直接跳过并打印。** 规范要求两者一致，加载器就把这条要求变成一次启动检查，而不是留给你在运行时排查。
- **`catalog()` 里只出现三个字段**：名字、描述、路径。它常驻系统提示，多写一个字段就是向所有请求多收一点税。

## 5.4.2 正文怎么放进上下文

第 2 层有个实现选择：模型怎么「读」到 `SKILL.md` 的正文？

两个方案。

**方案 A：用已有的 `fs_read`。** 技能包就是磁盘上的一个目录，Harnex 上一章已经会读文件。清单里把路径写出来，模型需要时自己读。

**方案 B：新增一个 `load_skill` 工具。** 模型传技能包名字，harness 去读文件、返回正文。

方案 B 更「正规」，好处是明确：调用 `load_skill(name=...)` 是一次可记录的显式事件，第 12 章做 trace 时能直接看到「这一轮加载了哪个技能包」。它还能顺手做权限校验——只允许读技能目录下的文件。

但这一章选 **方案 A**，有两个理由。

第一，**不要新增不必要的工具**：工具越多，模型越难选。每多一个工具，菜单就长一行；而这里没有任何新能力——读文件已经有了。

第二，**它更贴合格式的定义**：`SKILL.md` 不是某个 API 的资源，它就是文件系统上的一个文件。用「读文件」来加载技能包，说明你理解了这套格式的形态；用「调接口」来加载，就给这层知识加了一个它本来不需要的中间层。

> 如果哪天你发现需要审计「谁在什么时候加载了哪个技能包」，再把它升级成方案 B 也不迟——那时候你有具体的需求，而不是提前设计。

## 5.4.3 装进 Harnex

改动只有一处：主循环多收一个 `system` 参数，并在会话开始时放进 `messages`。

```python
# harnex/loop/agent.py —— Harnex v0.3：系统提示里多一段技能清单，循环逻辑一行没改
import asyncio
import json

from build_registry import build_registry
from llm import chat
from skills import SkillPackLoader

MAX_STEPS = 8
BASE_PROMPT = "你是一个能读写文件、执行任务的助手。回答简短、准确，不确定就问。"


def build_system_prompt(loader: SkillPackLoader) -> str:
    catalog = loader.catalog()
    return f"{BASE_PROMPT}\n\n{catalog}" if catalog else BASE_PROMPT


async def run(user_input: str, registry, system: str) -> str:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user_input}]
    for step in range(MAX_STEPS):
        msg = chat(messages, tools=registry.schemas())
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = await registry.call(call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "（步数超限，已强制停止）"


async def main() -> None:
    registry = build_registry()
    loader = SkillPackLoader()
    loader.discover()
    system = build_system_prompt(loader)
    print(f"已加载 {len(loader.packs)} 个技能包，清单 {len(loader.catalog())} 字符")
    while True:
        q = input("你> ")
        if q in ("exit", ""):
            break
        print("Harnex>", await run(q, registry, system))


if __name__ == "__main__":
    asyncio.run(main())
```

对比第 4 章的 `run()`，**熔断、追加顺序、终止判断、工具调用那几行，一个字都没动。** 技能包层的接入方式，和工具层一样：往系统提示里加一段、往磁盘上放一个目录，内核循环不知道这两层存在。

把 5.2 节写的 `weekly-report` 放进 `skills/`，跑起来：

```text
已加载 1 个技能包，清单 165 字符
你> 把本周的工作整理成周报
Harnex> 我先确认时间和本周的记录。
        调用 now（返回：2026-10-30，周五）
        列出 notes/，读取本周的 4 份日志
        按口径分成进展 6 条、风险 1 条、待办 3 条
Harnex> 周报在 reports/2026-W44.md。
        风险一栏只有一条：第三方接口联调延迟，对策是周三前切到 mock。
        其中「移动端适配」日志里没写验收结果，我先标了「待确认」。
        要调整哪里吗？
```

注意 `Harnex>` 后面那几行的顺序：**它先调 `now`、翻了日志，才动笔。** 说明「先看数据再写」这条指令生效了——它就是清单里那句话。

（这一节演示时 `skills/` 里只有刚写的 `weekly-report`。本章代码目录里还会多一个 `release-runbook`——5.5 节才写它——那时这行会变成「已加载 2 个技能包，清单 292 字符」。清单长度按「只算清单」量，不含系统提示里那几句固定的话。）

## 5.4.4 测描述能不能触发

技能包能生效的前提，是描述在被需要的时候能被想起来。5.3 节说这两行字杠杆最高，现在拿数据量一量。

准备 10 个任务：5 个应该触发 `weekly-report`（「把本周的工作整理成周报」「帮我写份 weekly」「日记都在 notes 里，出一份周报」「这周的事怎么分类汇报」「我们团队的周报口径是什么」），5 个不该触发（「读一下 README 的开头」「现在几点了」「搜一下仓库里的 TODO」「把 config 里的端口改成 8080」「解释一下这个函数在干什么」）。然后换三种描述各跑一遍：

| 写法 | 应该触发的 5 个 | 不该触发的 5 个 | 合计 |
| --- | --- | --- | --- |
| A「生成周报。」 | 2/5 | 5/5 | 7/10 |
| B「帮助处理工作汇报相关的各种事情。」 | 5/5 | 1/5 | 6/10 |
| C「按团队口径把本周工作整理成一份周报。当用户提到周报、weekly、本周总结、整理这周做了什么时使用。」 | 5/5 | 5/5 | **10/10** |

三种写法，是同一条规律的两个失效方向，加一个正解：

- **写法 A 太窄。** 它只说清了「做什么」，没说「什么时候用」。用户说「日记都在 notes 里，出一份周报」时，模型没有把这句话和「生成周报」连起来——**漏触发（under-triggering）**，表现为技能包装了等于没装。
- **写法 B 太宽。** 「工作汇报相关的各种事情」把日报、月报、汇报 PPT 全圈了进来，于是「把 config 里的端口改成 8080」这种完全无关的任务也会去加载它——**误触发（over-triggering）**，表现是正文反复污染上下文，还挤占了别的技能包的位置。
- **写法 C 是正解。** 它做了两件事：前半句给「做什么」，后半句给「什么时候用」，并且**把用户真会说的词直接写进描述里**（周报、weekly、本周总结）。模型不需要推理，只需要匹配。

这套用例不是一次性的，它是**回归测试集**——改动描述之后要重跑一遍，看有效触发率和误触发率有没有变差。5.7 节讲怎么把这件事做成流程。

> **与第 4 章的呼应**：上一章我们说，工具的 `description` 决定模型**选不选**它；这一章我们说，技能包的 `description` 决定模型**装不装**它进上下文。两处是同一个字段、同一种失败方式——**写含糊了，都不会报错，只会安静地不生效。**

到这一步，Harnex 的能力层齐了：动作可插拔（MCP），知识也可插拔（SKILL.md）。但那三个可选目录里，`scripts/` 还一个字没写。下一节处理 `scripts/`——以及为什么有些步骤不该让模型即兴发挥。
