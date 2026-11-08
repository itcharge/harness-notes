# harnex/reliability/bench.py —— 每个任务一条硬判据：返回 True 就是成功，None 是判不成
import subprocess


def check_import_cleanup(cwd):
    """跑一遍测试。返回 True / False / None：None 表示这条判据没跑起来。"""
    # shell=True 才让 "pytest -q" 这一整串当成命令执行；capture_output 把输出收起来，不刷屏。
    finished = subprocess.run("pytest -q", shell=True, cwd=cwd, capture_output=True)
    # 127 = 这台机器没装 pytest；5 = 一个测试都没收集到。
    # 两种都是「判不成」，不能算任务失败，交回 None 让调用方记成 check_error。
    if finished.returncode in (5, 127):
        return None
    # 判的是退出码，不是输出文字。模型说「我做完了」不算数，这里才算。
    return finished.returncode == 0

# 用法：print(check_import_cleanup("codes/ch10/harnex_v0.8"))
# 预期输出：True（测试全过）、False（有测试没过）、None（环境里没有 pytest，判不了）


# harnex/reliability/bench.py（续）—— 固定任务集 × N 轮：统计成功率与失败类型分布
def run_suite(tasks, run_once, rounds=5):
    """tasks 是 [{"name":..., "goal":..., "check":...}] 的清单。
    run_once(goal) 返回 {"ok": True/False/None, "kind": 失败类型}。"""
    total = 0
    passed = 0
    kinds = {}

    for round_no in range(rounds):
        for task in tasks:
            total = total + 1
            outcome = run_once(task["goal"])

            ok = outcome["ok"]
            if ok is None:
                # 判据自己没跑起来（比如脚本崩了）。这不是任务失败，单独记一笔。
                kinds["check_error"] = kinds.get("check_error", 0) + 1
                continue
            if ok:
                passed = passed + 1
                continue

            # kinds.get(k, 0) 的意思是「没有这个 key 就先当 0」，省掉一次 if。
            kind = outcome.get("kind")
            if not kind:
                kind = "unknown"
            kinds[kind] = kinds.get(kind, 0) + 1

    if total > 0:
        rate = round(passed / total, 3)
    else:
        rate = 0.0
    return {"total": total, "passed": passed, "rate": rate, "failures": kinds}


if __name__ == "__main__":
    # 一个假的跑批函数：凡是 goal 里带「崩」的，都当成超时失败。
    def fake_run_once(goal):
        if "崩" in goal:
            return {"ok": False, "kind": "timeout"}
        return {"ok": True, "kind": None}

    tasks = [
        {"name": "写报告", "goal": "写一份周报", "check": None},
        {"name": "改配置", "goal": "会崩的那一件", "check": None},
    ]
    print(run_suite(tasks, fake_run_once, rounds=2))

# 预期输出（一行）：
# {'total': 4, 'passed': 2, 'rate': 0.5, 'failures': {'timeout': 2}}
