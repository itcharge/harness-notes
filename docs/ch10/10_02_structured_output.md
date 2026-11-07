# 10.2 结构化输出：把自由文本关进笼子

## 10.2.1 后面的程序要能读懂

回到上一节第三次那个失败——37 条归错了类。它没崩，你对它当时也没意见，直到脚本去读输出。

先把一个词说清：**自由文本**，指没有固定格式的一段话。多长、怎么断句、用什么词，全由写的人定。人读不费劲，程序读就难。

**任何要进入程序的模型输出，都是一段要由人写代码解析的自由文本。** 解析（把一段文字读成程序能直接用的结构）这一步，是可靠性问题最大的来源。解析器假设一种格式，模型每次却在重新发明格式。

第 2 章讲结构化输出，重点在「让模型更好理解你的意图」。这里换个角度——**目的是让下游不必猜。**

## 10.2.2 约束格式，和事后检查

要让下游不必猜，第一件事是把输出套进固定格式。让模型吐出合规结构有两条路。

**第一条是约束解码**。先交代三个词：schema 是「输出该长什么样」的说明书；token 是模型写字的最小单位，约等于一个字；服务端是真正跑模型的那台机器。约束解码就是让服务端在生成时按 schema 卡住每一步能写什么，模型物理上写不出不合 schema 的内容。

这条路 2024 年 8 月之后才可用。OpenAI 那时发布 Structured Outputs（结构化输出功能）：在函数定义里设 `strict: true`，或在 `response_format` 里传 `json_schema`，输出保证匹配你给的 schema——他们的复杂 schema 评测里，新模型 100%，上一代不到 40%。而更早的 JSON mode 只保证「输出是合法 JSON」，**不保证符合你的 schema**。

**第二条是校验加重试**：自己写一个校验器（拿说明书去核对输出的一段代码）；不合规就把错误喂回去，让它再写一次。

关键判断是：**第二条路不能省。** 三个理由：

- 它依赖服务端和模型支持。换个模型、换个 provider（提供模型服务的公司），或跑本地权重（把模型文件下到自己机器上跑），这能力可能就没了。
- 它保证的是 **结构合规，不是内容正确**。字段名对了、枚举合法了，第 37 条照样可以归错类。
- 你迟早还要校验 **它管不到的东西**：文件是否真的存在、这个 ID 是否真在库里。

所以分工是：**能用约束解码就用，省掉一大半失败；但校验器永远保留，守住剩下的一小半。**

## 10.2.3 格式说明的三条原则

两条路都绕不开 schema，所以 schema 得自己写。先看一个不好的：

```json
{"type": "object",
 "properties": {"result": {"type": "string"}},
 "required": ["result"]}
```

这就是把自由文本装进一个叫 `result` 的笼子，笼子没有栅栏。

**一、字段少而必要。** 每加一个字段，都是模型要多照顾的一件事，也是多一个出错机会。本书的骨架里就列过一条这样的错误：「schema 过严：20 个字段全必填」。所以写的时候要问一句：**下游真会用它吗？**

**二、枚举代替自由文本。** 分类最容易出错的不是「没分类」，是「自创了一个类别」。把它写进 `enum`（枚举：允许出现的那几个值）：

```json
{"type": "object",
 "properties": {
   "items": {"type": "array", "items": {
     "type": "object",
     "properties": {
       "id": {"type": "integer"},
       "category": {"type": "string",
                    "enum": ["物流", "售后", "质量", "价格", "其他"]}
     },
     "required": ["id", "category"],
     "additionalProperties": false}}},
 "required": ["items"],
 "additionalProperties": false}
```

`enum` 把分类标准**从模型的措辞搬进代码**：只能选这五个之一，选不出来就用「其他」——而「其他」占了多少，本身就是个能盯着看的数。

**三、必填与可空明确。** 一个字段是「一定要有」还是「可能没有」，必须写死。含糊的代价是模型有时给 `null`（空值），有时给空串，有时干脆不给，解析器得同时处理三种。配一条习惯：`additionalProperties: false`。少写它，模型会热情地加上几个你没要的字段，悄悄流进下游。

## 10.2.4 一个小检查器

schema 写好了，还得有东西拿着它去查。这件事不必引第三方库：覆盖 `type` / `required` / `enum` / `properties` / `items` 五种关键字就够，六十行上下，还带一个能直接跑的示例：

```python
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
```

两处设计点：

- **错误里带路径。** `$.items[37].category` 比「校验失败」有用得多——喂回模型后，它真知道该改哪一条。
- **返回错误列表而不是抛异常**（抛异常：报错并中断，把整个程序带停）。`bool(validate(...))` 是判定，`validate(...)` 就是喂回去的内容。这还是 4.2 那条规矩：**校验结果是数据，不是异常。**

## 10.2.5 格式错了就让它改

有了校验器，调用就是一个小循环：

```python
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
```

函数末尾那个 `return None` 很重要：**重试耗尽后，它有责任向上报告失败，而不是硬凑一个结果**——这是 9.3「会放弃的 Agent 才可信」在调用层的版本。

重试提示里有个细节：**喂回去的是校验器报错原文，不是「格式不对，请重试」。** 前者直接告诉它第 37 条的 `category` 不在枚举里；泛泛的提示学不到东西，下一轮大概率再错。

还有一个便宜技巧——**把校验规则也写进提示**：`enum`、必填字段，第一次请求就告诉模型。校验器管「错了能不能发现」，提示管「尽量别错」，**两者不是替代关系**。

## 10.2.6 括号和引号坏了怎么修

校验器能跑，前提是先拿到一段能解析的 JSON。可模型不总给干净的 JSON。真实轨迹里常见：

| 你收到的 | 原因 |
| --- | --- |
| 被三个反引号包着 | 它当代码块输出了 |
| `{…},` | 多了个尾随逗号 |
| `{…}` 后面跟着「以上是分类结果」 | 它补了一句解释 |
| `{“分类”: …}` | 引号是中文弯引号 `“ ”` |
| `\ufeff{…}` | 开头多了个 BOM（文件开头的隐形标记） |

`json.loads` 一个都不认，所以解析要做成**尽力而为**：

```python
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
```

两处刻意不做：

- **只修「壳」，不修「内容」。** 剥代码块、掐前后废话、删尾随逗号，都发生在结构层；而中文弯引号、全角标点**可能出现在字段值内部**。全局替换分不清「结构里的标点」和「值里的标点」，会把本来正确的值改坏。这类错误交回模型重答，**因为一个悄悄改错的字段比一次解析失败更麻烦**。
- **解析失败返回 `None`，不抛异常。** 和 4.2 的铁律同一条：失败是一种返回值。它只是「尽力」，不是「兜底」。


解析这一关过了，还有一关：JSON 拿到了，可内容不合规。这时候你有三个选择，不是「哪个最好」，而是「在不同失败上各自更划算」：

| 策略 | 做法 | 代价 |
| --- | --- | --- |
| **重新请求** | 原封不动再要一次 | 一次完整调用；提示没变，可能重犯 |
| **局部修补** | 把错误清单喂回去，只让它改 | 一次调用；错误太多时可能改出新错 |
| **降级到自由文本** | 放弃结构，收下散文 | 下游要人来读；好处是任务不断 |

选法：

- **格式完全跑偏**（没 JSON、字段大面积缺失）→ 重新请求，并强化格式说明。
- **结构对了、少数值不合规** → 局部修补。最常见的场景，收益最高的一档。
- **重试耗尽** → 降级并标记。**留下不结构化但有用的结果，比空结果好**；关键是必须标记出来，别让下游当成合规数据。

第三条最容易被漏掉。「降级」听起来像认输，其实是**把失败成本从「任务中断」压到「一条人工看一眼的记录」**。前提是留痕（把「这条没按格式来」记下来）——否则就制造了 10.1 那种「看着对其实错」。


> **一、凡是下游要读的内容，都必须有 schema，并且被真的校验过。**
> **二、校验失败不是异常，是一次可以处理的返回。**

第一条把「格式」从口头约定变成代码约束；第二条把它接进 10.1 的三类失败——结构问题是最典型的可修正失败。

下一节处理另一类：结构完全正确、但外部世界正在抖动的失败。
