# harnex/tools/misc.py —— 时间工具 + 一个故意报错的教具
from datetime import datetime


def now(args: dict) -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def delete_note(args: dict) -> str:
    """教学道具：一个一定会失败的工具。"""
    filename = args["filename"]    # 要删的文件名，由模型从用户的话里读出来
    if filename == "日记.txt":
        return ("错误：日记.txt 不能直接删。"
                "请先用 fs_read(path='日记.txt') 看一遍内容，"
                "或改删副本 filename='日记-副本.txt'。")
    raise RuntimeError("删除功能还没接上")
