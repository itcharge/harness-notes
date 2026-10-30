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
