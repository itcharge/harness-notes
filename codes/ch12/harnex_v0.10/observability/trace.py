# harnex/observability/trace.py —— span：一段工作装上开始与结束，耗时当场落盘
# 只用标准库，不用 pip 装。要跑这段，先准备一个 log 对象：
# 它只要能调 append(dict) 就行，普通列表就可以。
import time
import uuid
from contextlib import contextmanager


# @contextmanager 是个装饰器。它让下面这个函数能配 with 用：
# 进 with 时先跑 yield 之前那段，出 with 时再跑 finally 那段。
# 所以函数里出现了 yield —— 这里的 yield 只是「把控制权交回去一会儿」，不产出数据。
@contextmanager
def span(log, node, name, parent_id=None, **fields):
    """用 with 包住一段工作：进出各落一条事件，耗时当场记下。

    多传的关键字参数（**fields）会原样放进记录，留给以后看板用。
    """
    span_id = uuid.uuid4().hex[:12]        # 12 位随机编号，用来互相挂
    record = {"id": span_id, "parent_id": parent_id, "node": node,
              "name": name, "status": "ok"}
    record.update(fields)                  # 想额外记的字段，直接并进来

    start_time = time.monotonic()          # 单调时钟，只拿它算差值
    log.append({"kind": "span_start", "span_id": span_id,
                "parent_id": parent_id, "node": node, "name": name})
    try:
        yield record
    except Exception:
        record["status"] = "error"        # 抛出去的异常也照样记一笔
        raise
    finally:
        # 不管上面成没成，都得补一条结束事件，否则这一段永远悬着
        elapsed = time.monotonic() - start_time
        end_event = {"kind": "span_end", "span_id": span_id,
                     "duration_ms": round(elapsed * 1000)}
        for key in record:
            if key in ("id", "parent_id", "node", "name"):
                continue
            end_event[key] = record[key]
        log.append(end_event)


# harnex/observability/trace.py（续）—— project_trace：把平铺的事件折成一棵树
def project_trace(events):
    """从会话日志投影出节点树。日志一个字节没改，只是换个读法。"""
    nodes = {}          # span_id → 节点
    order = []          # 按落盘顺序记住都有哪些 span
    for event in events:
        span_id = event.get("span_id")
        if not span_id:
            continue                      # 没带 span_id 的事不参与拼树
        kind = event["kind"]
        if kind == "span_start":
            node = {"id": span_id, "parent": event.get("parent_id"),
                    "node": event["node"], "name": event["name"],
                    "duration_ms": None, "tokens_in": 0,
                    "tokens_out": 0, "status": "ok", "children": []}
            nodes[span_id] = node
            order.append(span_id)
            continue
        if kind == "span_end":
            node = nodes.get(span_id)
            if node is None:
                continue                  # 只有结束没有开始：日志被截断了，跳过
            for key, value in event.items():
                if key in ("kind", "span_id", "parent_id"):
                    continue
                node[key] = value         # 结束事件上的字段全部并进节点

    # 第二遍才挂子节点。这样与事件顺序无关：并行的两支谁先落盘都对
    roots = []
    for span_id in order:
        node = nodes[span_id]
        parent_id = node["parent"]
        if parent_id and parent_id in nodes:
            parent = nodes[parent_id]
            parent["children"].append(node)
        if not parent_id:
            roots.append(node)     # 没父的才是树根；父不在日志里的不挂也不当根
    return {"index": nodes, "roots": roots}


# harnex/observability/trace.py（续）—— 从日志重建 trace 库：删了也不心疼
import sqlite3


def rebuild_trace(db_path, sessions_dir):
    """丢掉旧库，从全部 JSONL 重放一遍。任何时刻都可执行。

    这里用到第 6 章的 load_all_sessions(sessions_dir)：它把每个会话的
    「事件列表 + 会话 id」一个一个交出来。
    """
    # 最常见的报错是 sqlite3.OperationalError：db_path 的目录不存在
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS spans")   # 重建就是不认旧数据，先清空
    conn.execute("""CREATE TABLE spans (
        span_id TEXT PRIMARY KEY, parent_id TEXT, session_id TEXT,
        node TEXT, name TEXT, duration_ms INTEGER,
        tokens_in INTEGER, tokens_out INTEGER, status TEXT)""")
    rows = 0
    for events, session_id in load_all_sessions(sessions_dir):
        tree = project_trace(events)
        for node in tree["index"].values():
            conn.execute("INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?)",
                         (node["id"], node["parent"], session_id, node["node"],
                          node["name"], node["duration_ms"],
                          node["tokens_in"], node["tokens_out"], node["status"]))
            rows += 1
    conn.commit()
    conn.close()                                # 不关的话文件一直被占着
    return rows
