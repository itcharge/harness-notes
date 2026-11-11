# harnex/apps/server/app.py —— Web 控制台后端：一条 WebSocket 接一个会话
# 依赖：pip install fastapi uvicorn。不用 API key 也能起服务，
# 只是真的发一句话之后，模型那一步会报错。
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


@app.websocket("/ws/{session_id}")
async def ws_chat(ws: WebSocket, session_id: str):
    await ws.accept()

    log = SessionLog.load(session_id)              # 第 6 章：状态从日志读，不存内存
    registry = build_registry()                    # 第 4 章：工具装配线
    gate = ApprovalGate(log, ask=make_asker(ws))   # 11.4 的闸门，问法换成网页

    # 推一条事件给前端。type 和日志的 kind 同名，前端不用再翻译一遍
    async def emit(event):
        await ws.send_json(event)

    try:
        while True:
            frame = await ws.receive_json()

            if frame["type"] == "user_message":
                await run_turn(frame["text"], registry, log, gate, emit)
                await emit({"type": "turn_done"})

            elif frame["type"] == "confirm":
                resolve_approval(frame["key"], bool(frame["verdict"]))

    except WebSocketDisconnect:
        # 断开不等于任务失败：日志已落盘，接着跑靠 10.4 的 resume
        pass

# 启动：uvicorn harnex.apps.server.app:app --reload
# 跑起来看到：浏览器打开 http://127.0.0.1:8000，发一句话，字一段一段冒出来。
# 关掉标签页、再打开同一个会话，历史还在——因为它是从日志重放出来的。
