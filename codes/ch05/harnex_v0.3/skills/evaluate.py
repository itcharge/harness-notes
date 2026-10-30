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
