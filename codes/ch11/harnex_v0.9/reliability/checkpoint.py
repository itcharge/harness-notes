# harnex/reliability/checkpoint.py —— 副作用账本：动手前记 begin，成功后记 done
# 这里的 log 就是第 6 章的 SessionLog：append() 往里加一行，events() 读回全部。
class Ledger:
    """副作用账本。key 标识一件具体的事，不是一类事。"""

    def __init__(self, log):
        self.log = log

    def done(self, key):
        """这件事已经成功做过吗？"""
        for event in self.log.events():
            if event["kind"] == "effect_done" and event["key"] == key:
                return True
        return False

    def begin(self, key, note):
        # 动手之前先落一条 begin。崩在中间时，这条没有配对的 done 就是证据。
        self.log.append("effect_begin", key=key, note=note)

    def commit(self, key, result):
        self.log.append("effect_done", key=key, result=result)

    def last(self, key):
        """取上一次成功的结果，供重复执行时直接返回。"""
        # 从后往前找：同一个 key 理论上只有一条 done，倒着找最快碰到。
        for event in reversed(self.log.events()):
            if event["kind"] == "effect_done" and event["key"] == key:
                return event["result"]
        return None

# 用法（要先有一个第 6 章的 SessionLog）：
#   ledger = Ledger(log)
#   ledger.begin("send-mail-42", note="给客户 42 发确认信")
#   ledger.commit("send-mail-42", "ok")
#   print(ledger.done("send-mail-42"))    # True
#   print(ledger.last("send-mail-42"))    # ok


# harnex/reliability/checkpoint.py（续）—— 幂等执行：做过就返回上次结果，没做过才动手
# 参数里的 *args 是「把后面的参数原样收进来」，再原样转交给 action。
def run_effect(ledger, key, action, *args):
    """幂等地执行一个有副作用的动作。崩溃后重放，不会重复执行。"""
    cached = ledger.last(key)
    if cached is not None:
        return "（已执行过，直接返回上次结果）" + cached

    # note 只留前 200 字：日志是给人扫的，整段参数塞进去会把它淹掉。
    ledger.begin(key, note=repr(args)[:200])

    try:
        result = action(*args)
    except Exception as exc:
        # 失败就不写 done。日志里留下一条没有配对的 begin，下次一看就知道要重做。
        return f"错误：{key} 执行失败：{exc}"

    ledger.commit(key, str(result))
    return str(result)


# harnex/reliability/checkpoint.py（续）—— 任务级恢复：回到「下一步要做什么」，不回放历史
def resume(ledger):
    """从日志里恢复出一个任务的进度视图：哪些做完了、下一步是什么。"""
    events = ledger.log.events()

    # 先收「已经落地的副作用」有哪些 key，后面拿它给每一步对账。
    done_keys = set()
    for event in events:
        if event["kind"] == "effect_done":
            done_keys.add(event["key"])

    items = project_todos(events)          # 9.2 的清单投影：最后一条 todo_update
    steps = []
    for item in items:
        effect_key = item.get("effect_key")
        recorded = False
        if effect_key in done_keys:
            recorded = True
        steps.append({
            "id": item["id"],
            "task": item["task"],
            "status": item.get("status", "todo"),
            "effect_key": effect_key,
            "recorded": recorded,
        })

    # 「下一步」就是第一条还没做完的。恢复要的是这个，不是把历史重放一遍。
    pending = []
    for step in steps:
        if step["status"] != "done":
            pending.append(step)

    next_step = None
    if pending:
        next_step = pending[0]

    return {"steps": steps, "pending": pending, "next": next_step}

# 用法（依赖第 9 章的 project_todos 和第 6 章的 SessionLog）：
#   view = resume(ledger)
#   print(view["next"])   # {'id': 3, 'task': '改配置', 'status': 'doing', ...}
