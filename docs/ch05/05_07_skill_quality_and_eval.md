# 5.7 技能包的质量与评测

## 5.7.1 失败时往往没有报错

先把这一节要解决的痛点说准。

工具的失败很好发现：参数错了有异常、路径越界有错误文本、超时会有日志。**技能包的失败是无声的。** 描述写得含糊，结果就是模型压根没想起它——而你看到的现象只是「它又没用规范提交」，看起来像是模型不行，其实是你的描述不行。

更麻烦的是它**在测试时是好的**。你写完 `weekly-report`，随手打一句「整理一下周报」，它触发了；于是你以为成了。上线后用户说的是「这周的事帮我捋一捋」，模型没连上，技能包再也没出现过。**你没有任何告警可看。**

所以技能包需要一套自己的测试。它的形式和你想象的差不多——**一份用例集，跑一遍，看触发对不对**。

## 5.7.2 该触发和不该触发各一半

规范里对这件事给了明确建议：**准备一批查询，一半该触发，一半不该触发。** 这就是全部方法论，剩下的是把它做实。

对 `weekly-report`，10 个用例的样子：

```text
【正向 5 条】必须触发
  把本周的工作整理成周报
  帮我写份 weekly
  日记都在 notes 里，出一份周报
  这周的事怎么分类汇报
  我们团队的周报口径是什么

【反向 5 条】一个都不许触发
  读一下 README 的开头
  现在几点了
  搜一下仓库里的 TODO
  把 config 里的端口改成 8080
  解释一下这个函数在干什么
```

两边的考察目标不同，命名也不一样：

- **正向用例测召回**——该触发的时候，它有没有被想起来。漏掉一条就是一次 **漏触发**。
- **反向用例测精度**——不该触发的时候，它有没有忍住。多触发一条就是一次 **误触发**。

**两种失败的成本是不对称的**，这一点决定了用例该怎么配比。

误触发的代价是 token：白读了一篇 `SKILL.md`，浪费几千 token，但结果通常还是对的——模型读完发现不相关，会自己绕开。漏触发的代价是 **功能失效**：技能包存在但用不上，而且不留痕迹。**误触发是浪费，漏触发是欺骗。** 所以反向用例要给足——它们是唯一能发现「描述太宽」的手段，而「太宽」恰恰是最容易犯的错。

## 5.7.3 写成可以反复跑的脚本

用例集如果靠手点，跑第三次就没人跑了。把它做成脚本，成本才是常数：

```python
# harnex/skills/evaluate.py —— 技能包触发测试集：只看模型有没有去读 SKILL.md
import asyncio
import json
from pathlib import Path

from build_registry import build_registry
from loop.agent import build_system_prompt
from llm import chat
from skills import SkillPackLoader

# (任务, 期望触发的技能包)；None 表示不该触发任何技能包
CASES = [
    ("把本周的工作整理成周报", "weekly-report"),
    ("帮我写份 weekly", "weekly-report"),
    ("日记都在 notes 里，出一份周报", "weekly-report"),
    ("这周的事怎么分类汇报", "weekly-report"),
    ("我们团队的周报口径是什么", "weekly-report"),
    ("读一下 README 的开头", None),
    ("现在几点了", None),
    ("搜一下仓库里的 TODO", None),
    ("把 config 里的端口改成 8080", None),
    ("解释一下这个函数在干什么", None),
]


async def loaded_skills(task: str, registry, system: str) -> set:
    """跑最多三轮，收集模型读过的那些 SKILL.md 所属的技能包名。"""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]
    hit = set()
    for _ in range(3):
        msg = chat(messages, tools=registry.schemas())
        messages.append(msg)
        if not msg.tool_calls:
            break
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            if call.function.name == "fs_read" and "SKILL.md" in str(args.get("path", "")):
                hit.add(Path(args["path"]).parent.name)
            result = await registry.call(call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return hit


async def main() -> None:
    registry = build_registry()
    loader = SkillPackLoader()
    loader.discover()
    system = build_system_prompt(loader)

    passed = 0
    for task, expect in CASES:
        hit = await loaded_skills(task, registry, system)
        ok = (not hit) if expect is None else (hit == {expect})
        passed += ok
        print(f"{'通过' if ok else '失败'}  {task}  "
              f"（期望 {expect or '不触发'}，实际 {'、'.join(hit) or '不触发'}）")
    print(f"\n{passed}/{len(CASES)}")


if __name__ == "__main__":
    asyncio.run(main())
```

三点说明：

- **判定标准是「有没有读 `SKILL.md`」，不是「答案对不对」。** 这是知识层的评测，被测对象是 **加载行为**。答案质量属于第 13 章的任务级评测——两层分开测，出问题时才定位得到是哪一层坏了。
- **更不要顺带测「读了之后有没有照做」。** 上面这个脚本只统计加载，不看模型有没有照着正文执行。理由和上一条一样：混在一起测，失败了你分不清是「没加载」还是「加载了但没遵守」——而这两种问题的修法完全不同，前者改描述，后者改正文。
- **用例要能被别人跑。** 它依赖你的技能目录和模型，所以跟着仓库走。**一份存在但没人跑的测试，等于没有测试。**

跑一遍，你会得到一张直白的表：

```text
通过  把本周的工作整理成周报  （期望 weekly-report，实际 weekly-report）
通过  帮我写份 weekly  （期望 weekly-report，实际 weekly-report）
失败  日记都在 notes 里，出一份周报  （期望 weekly-report，实际 不触发）
...
8/10
```

那个失败项就是下一次改描述的依据——它告诉你**用户会说的某种说法，你的描述里没有**。把「日记」两个字加进描述，再跑一遍。

再跑的结果就是判据：这一条从「失败」翻成「通过」，其余九条没变差，改动才算成立。**一次只动一处，动完看那张表**——这就是回归测试最朴素的形态。

## 5.7.4 改了版本要再测一遍

有了脚本，下一步是让它别退化。

技能包会改。你加了一条边界情况、删了一句过时的说明、调整了触发关键词。这些改动分两类：改正文，改的是「想起我之后做得好不好」；改描述，改的是「模型还会不会想起我」。**后者没有任何静态检查能覆盖，只能跑一遍看。**

把版本号写进 `metadata`：

```yaml
metadata:
  author: harnex-book
  version: "1.2"
```

这不是装饰。它让「这次触发率下降」这件事有得可查：失败的那条用例是 1.1 就有的，还是 1.2 改描述时引入的？没有版本号，你只有一份「现在的结果」和一段模糊的记忆。

回归的粒度也不用太细。**改描述必跑全量，改正文可以不跑**——正文不影响触发，它影响的是「触发之后做得好不好」，那是另一套评测（第 13 章）。**每一次都跑全量，是另一种形式的没人跑。**

## 5.7.5 两个数字：门槛低，写好难

最后补两个数字，说明这件事有多普遍。

SkillsBench 的实测（86 个任务、11 个领域）给出了一个具体数字：装上整理过的技能库，任务通过率平均比不用技能高 **16.2 个百分点**——但 84 个可对比的任务里，有 16 个反而变差了。**技能包确实有用，前提是它被正确触发、并被遵守；用错了地方，它会拖后腿。**

但另一项独立分析更不客气：**238 个真实 `SKILL.md` 里，超过 99% 至少存在一处「技能包坏味道」，平均一个文件 10.5 处**——描述过宽、正文过长、脚本没有错误处理、依赖没写进 `compatibility`。这些坏味道很少随着版本迭代自然消失。

两个数字放在一起，结论很清楚：

> **技能包的门槛低到几乎人人都能写，但写好它需要的正是本章这几节——格式、渐进披露、脚本边界、触发测试、安装审计。**

这也解释了为什么第 13 章的评测体系在这里要先开一个口子。技能包是 **少数几种「写完不用编译、不用测试就能生效」的能力形态之一**，它把质量责任全部推给了作者。你可以在一个下午写出十个能用的技能包，也可以写出十个永远不触发的技能包——**两者在文件系统上长得一模一样。**

下一节处理最后一件事，也是风险最高的一件：**装别人的技能包。**
