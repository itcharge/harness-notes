# harnex/reliability/schema.py —— 极小的 JSON Schema 校验器：够用，且不引依赖
# 一张对照表：schema 里写 "string"，Python 这边就该是 str。查之前先按名字取出来。
_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def validate(data, schema, path="$"):
    """返回错误列表；空列表表示通过。错误里带路径，好让模型知道改哪一处。"""
    errors = []

    want = schema.get("type")
    if want in _TYPES and not isinstance(data, _TYPES[want]):
        # 类型都不对，下面几项就不用查了。
        return [f"{path}: 期望 {want}，实际是 {type(data).__name__}"]

    # True 在 Python 里是 int 的子类，isinstance(True, int) 为真。
    # 所以查「数量」「次数」这类字段时，true 会混过去，得单独挡一下。
    if want in ("integer", "number") and isinstance(data, bool):
        return [f"{path}: 期望 {want}，实际是 boolean（true/false 不算数字）"]

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: 值 {data!r} 不在允许的枚举里：{schema['enum']}")

    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: 缺少必填字段 {key!r}")

        # 每个字段拿它自己的小 schema 再查一层；路径要接上，模型才知道改哪一个。
        props = schema.get("properties", {})
        for key, sub_schema in props.items():
            if key in data:
                errors = errors + validate(data[key], sub_schema, f"{path}.{key}")

        # 模型常会热情地多给几个字段，additionalProperties: false 就是挡这个的。
        extra = []
        for key in data:
            if key not in props:
                extra.append(key)
        if schema.get("additionalProperties") is False and extra:
            errors.append(f"{path}: 出现了未定义的字段 {sorted(extra)}")

    if isinstance(data, list) and "items" in schema:
        # enumerate 同时给出「第几个」和「这个元素」，省掉手动取下标。
        for index, item in enumerate(data):
            errors = errors + validate(item, schema["items"], f"{path}[{index}]")

    return errors


if __name__ == "__main__":
    schema = {
        "type": "object",
        "required": ["category"],
        "properties": {"category": {"type": "string", "enum": ["物流", "售后"]}},
        "additionalProperties": False,
    }
    print(validate({"category": "物流"}, schema))
    print(validate({"category": "其他"}, schema))
    print(validate({"note": "x"}, schema))
    print(validate(True, {"type": "integer"}))

# 预期输出（四行）：
# []
# ["$.category: 值 '其他' 不在允许的枚举里：['物流', '售后']"]
# ["$: 缺少必填字段 'category'", "$: 出现了未定义的字段 ['note']"]
# ["$: 期望 integer，实际是 boolean（true/false 不算数字）"]


# harnex/reliability/schema.py（续）—— 校验 + 失败重试：把错误原文喂回去
# 这一段要联网：先设好环境变量 DEEPSEEK_API_KEY，chat() 在第 2 章的 llm/client.py 里。
def structured_call(prompt, schema, tries=3):
    """要求模型按 schema 返回；不合规就把错误喂回去让它改，最多 tries 次。"""
    message = prompt
    for attempt in range(tries):
        # 第 1 次发原题；第 2、3 次发的是「原题 + 上一次错在哪」。
        # 这一步最常见的报错：401 是 key 不对（重试没用），429 是被限流（等一会儿再来）。
        raw = chat([{"role": "user", "content": message}]).content

        data = extract_json(raw)
        if data is None:
            # 连 JSON 都没抠出来，只提醒它「只输出 JSON」，别把解释塞回去。
            message = prompt + "\n\n你上次的回复里没有可解析的 JSON。只输出 JSON 本身，不要写解释，不要包代码块。"
            continue

        errors = validate(data, schema)
        if not errors:
            return data

        # 把错误原文一条条列出来。只说「格式不对」，模型下一轮大概率再错一次。
        lines = []
        for one_error in errors:
            lines.append("- " + one_error)
        message = prompt + "\n\n你上次的 JSON 有这些问题，请改正后重新输出：\n" + "\n".join(lines)

    # 三次都没改成，返回 None，交给上一层按「不可恢复」处理。
    return None


# harnex/reliability/schema.py（续）—— 防御性解析：先剥壳，再修结构，最后才认输
import json
import re


def extract_json(text):
    """从模型回复里抠出 JSON 对象。失败了返回 None，不抛异常。"""
    body = text.strip().lstrip("\ufeff")      # 最前面有时带一个看不见的 BOM

    # 最常见的一层壳是代码块围栏：把围栏里那段挑出来。
    if "```" in body:
        for chunk in body.split("```"):
            piece = chunk.strip()
            if piece.startswith("json"):
                piece = piece[4:].strip()
            if piece.startswith("{"):
                body = piece
                break

    # 前后常夹着客套话，只取第一个 { 到最后一个 }。
    start = body.find("{")
    end = body.rfind("}")
    if start == -1 or end <= start:
        return None

    # 只剩一种毛病值得自动修：对象或数组末尾多一个逗号。其他一概不修，免得改坏。
    body = re.sub(r",(\s*[}\]])", r"\1", body[start:end + 1])

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        # 解析不了的，宁可返回 None 让上层重试，也不要硬凑一个结果。
        return None

    if isinstance(data, dict):
        return data
    return None


if __name__ == "__main__":
    print(extract_json('{"a": 1,}'))                    # 尾随逗号被修掉
    print(extract_json('结果在这里：{"a": 1} 以上。'))    # 前后的废话被掐掉
    print(extract_json('抱歉，我没法回答'))              # 没有 JSON，返回 None

# 预期输出（三行）：
# {'a': 1}
# {'a': 1}
# None
