# harnex/approval/gate.py —— 审批闸门：动手前问人，答案写进日志
# 这里第一次用 class：它只是把两样东西捆在一起——日志，和「怎么问人」。
# self 指「这一个闸门自己」；__init__ 是造它的时候跑一次，把两样存进去。
class ApprovalGate:

    def __init__(self, log, ask):
        self.log = log
        self.ask = ask          # 「怎么问用户」的回调：终端和网页问法不一样

    def decide(self, key, summary):
        """需要审批的动作先过这里。返回 True 才允许执行。"""
        # 先翻日志。崩溃重启后，同一个 key 不能问第二遍
        for event in self.log.events():
            if event["kind"] == "approval_granted" and event["key"] == key:
                return True
            if event["kind"] == "approval_denied" and event["key"] == key:
                return False

        # 日志里没有这个 key，才真的去问人
        self.log.append("approval_request", key=key, summary=summary)
        verdict = bool(self.ask(summary))        # 卡在这里，等用户点按钮

        if verdict:
            self.log.append("approval_granted", key=key)
        else:
            self.log.append("approval_denied", key=key)
        return verdict

# 跑起来看到：问一次 → 日志里多两条（request + granted）。
# 第二次拿同一个 key 进来，loop 在日志里命中，直接返回，不再问。
