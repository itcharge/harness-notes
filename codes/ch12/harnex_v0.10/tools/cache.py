# harnex/tools/cache.py —— 工具结果短时缓存：只缓存幂等的、不随时间变的调用
# 只用标准库（hashlib / json），不用 pip 装。
import hashlib
import json


def cache_key(tool, args):
    """参数要排序后再序列化，否则键序不同会算成两次调用。"""
    blob = json.dumps(args, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    short = digest[:16]                  # 16 位够用，键短一点好看
    return tool + ":" + short
