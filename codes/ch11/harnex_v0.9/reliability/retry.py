# harnex/reliability/retry.py —— 退避 + 抖动：等的时间要随机，不是 2 的幂
import random


def backoff(attempt, base=0.5, cap=30.0):
    """第 attempt 次失败之后，该等多少秒。返回的是一个随机数，不是一个固定值。"""
    # 这一轮的上限：0.5、1、2、4……但封顶在 cap。
    ceiling = min(cap, base * (2 ** attempt))
    # 在上限之内随便取一个：多个客户端才不会在同一秒一起醒来。
    return random.uniform(0, ceiling)


if __name__ == "__main__":
    # 每次运行的值都不一样，但一定落在后面注释说的范围里。
    print(round(backoff(0), 3))      # 0 到 0.5 之间
    print(round(backoff(3), 3))      # 0 到 4 之间
    print(round(backoff(20), 3))     # 0 到 30 之间，cap 封住了


# harnex/reliability/retry.py（续）—— 熔断器：三态，冷却后放一个请求探路
import time


class Breaker:
    """连续失败到阈值就断开；冷却之后只放一个请求出去试探。"""

    def __init__(self, threshold=3, cooldown=30.0):
        self.threshold = threshold     # 连着失败几次就断开
        self.cooldown = cooldown       # 断开之后先冷静多少秒
        self.fails = 0
        self.opened_at = 0.0
        self.state = "closed"          # closed 通 / open 断 / half_open 试探

    def allow(self):
        """现在能不能发起一次调用？"""
        if self.state == "closed":
            return True

        if self.state == "open":
            # monotonic 是只往前走、不受系统改时间影响的钟，量间隔必须用它。
            waited = time.monotonic() - self.opened_at
            if waited >= self.cooldown:
                self.state = "half_open"
                return True            # 只放这一个出去，探通了再全面恢复
            return False               # 冷却没到，一个请求都不发，钱就省在这

        return True                    # half_open：这一次探路放行

    def record(self, ok):
        """每次调用回来都记一笔。成功或失败，决定状态往哪边走。"""
        if ok:
            self.fails = 0
            self.state = "closed"
            return

        self.fails = self.fails + 1
        # 探路那次也失败，或者失败次数到阈值，就断开。
        if self.state == "half_open" or self.fails >= self.threshold:
            self.state = "open"
            self.opened_at = time.monotonic()


if __name__ == "__main__":
    breaker = Breaker(threshold=3, cooldown=30)
    for i in range(3):
        breaker.record(False)          # 模拟连着失败三次
    print(breaker.state)               # open
    print(breaker.allow())             # False：冷却期还没过

# 预期输出（两行）：
# open
# False
