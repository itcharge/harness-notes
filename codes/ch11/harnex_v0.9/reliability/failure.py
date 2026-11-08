# harnex/reliability/failure.py —— 三类失败的判定：依据是「重试能不能改变结果」
# 三份名单：把认识的失败名归好类，分类结果才是可复现的。
RETRYABLE = {"timeout", "connection_reset", "rate_limit", "server_error"}
FIXABLE = {"schema_violation", "bad_argument", "invalid_json"}
FATAL = {"not_found", "permission_denied", "precondition_failed"}


def classify(kind):
    """把一个失败名换成处理动作：retry 重试、repair 改一改再试、abort 停下报告。"""
    # 判断顺序有讲究：先看还能不能重试，再看能不能改，最后才认输。
    if kind in RETRYABLE:
        return "retry"
    if kind in FIXABLE:
        return "repair"
    if kind in FATAL:
        return "abort"
    # 认不出来的，按最坏情况处理：停下来，交给人看。
    return "abort"


# 这一段直接跑就行：python failure.py
if __name__ == "__main__":
    print(classify("timeout"))
    print(classify("bad_argument"))
    print(classify("not_found"))
    print(classify("谁也没见过这个错"))

# 预期输出（四行）：
# retry
# repair
# abort
# abort
