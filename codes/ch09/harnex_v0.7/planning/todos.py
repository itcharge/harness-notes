# harnex/planning/todos.py —— 待办清单：状态在日志里，每轮投影渲染进上下文
STATUS = {"todo": "[ ]", "doing": "[>]", "done": "[x]", "failed": "[!]"}
MARK = {"todo": "待办", "doing": "进行中", "done": "已完成", "failed": "失败"}


def project_todos(events: list[dict]) -> list[dict]:
    """当前清单 = 最后一条 todo_update 的 items；没有则返回空清单。"""
    latest: list[dict] = []
    for event in events:
        if event["kind"] == "todo_update":
            latest = event["items"]
    return latest


def render_todos(items: list[dict]) -> str:
    """把清单渲染成给模型看的一段文本。它每轮都会被拼进系统提示。"""
    if not items:
        return "（当前没有待办清单）"
    lines = ["当前待办清单："]
    for item in items:
        mark = STATUS.get(item.get("status", "todo"), "[ ]")
        lines.append(f"{mark} {item['id']}. {item['task']}")
        if item.get("done_when"):
            lines.append(f"      完成标准：{item['done_when']}")
        if item.get("note"):
            lines.append(f"      备注：{item['note']}")
    done_count = sum(1 for item in items if item.get("status") == "done")
    lines.append(f"进度：{done_count}/{len(items)} 已完成")
    return "\n".join(lines)


# harnex/planning/todos.py（续）—— 把两个清单工具绑到某一份日志上
def make_todo_tools(log) -> tuple:
    """返回 (set_todos, update_todo)，两者都把状态写回日志。"""

    def set_todos(args: dict) -> str:
        """写入或整体替换待办清单。items 为 [{task, done_when}, ...]。"""
        raw_items = args.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            return "错误：items 必须是非空列表，每一项至少要有一个 task 字段。"
        clean_items = []
        for i, item in enumerate(raw_items):
            if not isinstance(item, dict) or not item.get("task"):
                return f"错误：第 {i + 1} 项缺少 task 字段。"
            clean_items.append({"id": i + 1,
                                "task": str(item["task"]),
                                "done_when": str(item.get("done_when", "")),
                                "status": "todo"})
        log.append("todo_update", items=clean_items)
        return f"已写入 {len(clean_items)} 项待办：\n" + render_todos(clean_items)

    def update_todo(args: dict) -> str:
        """更新某一项的状态。status 取 todo / doing / done / failed。"""
        if args.get("status") not in STATUS:
            allowed = " / ".join(STATUS)
            return f"错误：status 只能是 {allowed}。"
        items = project_todos(log.events())
        index = int(args.get("index", 0))
        if index < 1 or index > len(items):
            return f"错误：清单里没有第 {index} 项，当前共 {len(items)} 项。"
        target = items[index - 1]
        target["status"] = args["status"]
        if args.get("note"):
            target["note"] = str(args["note"])
        log.append("todo_update", items=items)
        return "已更新：\n" + render_todos(items)

    return set_todos, update_todo
