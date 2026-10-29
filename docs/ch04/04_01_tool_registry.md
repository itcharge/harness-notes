# 4.1 从函数列表到工具注册表：粒度与依赖倒置

## 4.1.1 一个工具包含什么

第 3 章里，一个工具就是一个函数。这里把「工具」升级成「一份带说明书的记录」：

```python
# harnex/tools/registry.py —— Harnex v0.2：可插拔的工具层
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Tool:
    """一个工具 = 名字 + 说明 + 参数 schema + 执行函数 + 权限声明"""
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], str]
    scopes: list = field(default_factory=list)     # 权限声明：空 = 什么都没申请

    def schema(self) -> dict:
        """转成给模型看的那一项（第 3 章 TOOL_SCHEMAS 里的一项）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
```

五样东西，缺一不可。`name` 和 `handler` 第 3 章已经有了。这一章补另外三样：

- `description`：写给模型看的说明
- `parameters`：参数格式（schema），有哪些字段、哪些必填
- `scopes`：这个工具要什么权限

## 4.1.2 工具注册表

```python
class ToolRegistry:
    """工具的家：负责注册、校验、取用。循环只跟它打交道，不认识任何具体工具。"""

    def __init__(self, granted_scopes: set):
        self._tools: dict = {}
        self._granted = set(granted_scopes)        # 本次会话被授予的权限范围

    def register(self, tool: Tool) -> None:
        if not tool.scopes:
            raise ValueError(f"拒绝注册 {tool.name}：未声明任何权限（默认拒绝）")
        missing = [s for s in tool.scopes if s not in self._granted]
        if missing:
            raise ValueError(f"拒绝注册 {tool.name}：申请 {missing}，未获授予")
        if tool.name in self._tools:
            raise ValueError(f"拒绝注册 {tool.name}：名字已被占用")
        self._tools[tool.name] = tool

    def schemas(self) -> list:
        return [tool.schema() for tool in self._tools.values()]

    def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"错误：没有名为 {name} 的工具。可用工具：{', '.join(sorted(self._tools))}"
        try:
            result = tool.handler(args)
        except Exception as exc:                   # 兜底：绝不让异常抛穿循环
            return f"错误：{tool.name} 执行失败（{type(exc).__name__}: {exc}）"
        return result if isinstance(result, str) else str(result)
```

三个方法，各管一件事。注意留意每一处「拒绝」：

- **`register()` 会拒绝三种情况**：没写权限，拒绝。写了权限但这次会话没给，拒绝。名字重复，拒绝。从注册这一步就开始把关，而不是等到调用才检查。
- **`schemas()` 生成给模型看的清单**：把每个工具转成一条 schema。第 3 章那串 `TOOL_SCHEMAS`，现在直接从注册表里生成，加一个工具只需要改这一处。
- **`call()` 是唯一的执行出口**：找不到工具时，返回一段可读的错误，而不是抛异常。执行出错时，兜底捕获异常，转成可读的错误文本。第 3 章 3.2.3 节要求「工具结果必须是字符串」，现在从循环挪到了这里。异常到不了循环，循环又干净一点。

## 4.1.3 循环只跟注册表打交道

这是本章最关键的一处改动，代码只动了一行。先看第 3 章执行工具的三行：

```text
fn = TOOLS[call.function.name]                  # 按名字取出要执行的函数
args = json.loads(call.function.arguments)      # 模型给的参数：一段 JSON 文本
result = fn(args)                               # 把参数字典整个交给工具
```

再看改造后：

```text
args = json.loads(call.function.arguments)        # 模型给的参数：一段 JSON 文本
result = registry.call(call.function.name, args)  # 交给注册表：它负责找到并执行
```

**「按名字取函数」这一步没了。** 循环不再关心工具是函数、类方法，还是另一台机器上的进程。它只做一件事：把名字和参数交给注册表，拿回一段文本。

循环依赖注册表，不依赖某个具体工具。工具怎么写，循环不用知道。这就是标题里的「依赖倒置」。

所以工具可以随加随换：加二十个、用别的语言重写一个、甚至搬到另一台机器上。**循环一个字都不用改。**

## 4.1.4 没声明权限就不能用工具

上一节的工具可以随加随换，但注册表不是来者不拒。`register()` 先看它有没有写自己要什么权限：

```python
if not tool.scopes:
    raise ValueError(f"拒绝注册 {tool.name}：未声明任何权限（默认拒绝）")
```

如果 `scopes` 是空的，注册直接失败。**工具没写「我需要什么权限」，就不允许加载。** 没写就当不能用，这叫默认拒绝。

不能没写也让它用。模型自己只会输出文本，文本错了，文件还在。写文件、删数据、发请求会真的改掉东西，而这些操作只能靠工具来做。能改文件的工具一旦加载，一句写错的文本就会真的改掉文件。所以要不要加载，得先看它写没写自己要什么权限。`scopes` 就是这一行。

如果去掉上面这个检查，忘了写 `scopes` 的新工具会直接进来。它能改文件，注册表里却没有 `scopes` 声明，等于自动带上全部权限。忘写声明，又是最常见的失误。

`scopes` 里只记允许做的事。工具写上「写文件」，就只给写文件；没写上的，一律不给。这样的单子叫白名单。黑名单要你事先列出所有不该做的事，漏一条就放进去了。

注册这一步只回答「这个工具能不能加载」：自己声明权限，注册时核对，没声明就拒绝。它这次能不能跑、要不要先问你，留到第 15 章。权限声明就是插头上的额定功率，每个工具先把这行字印上，注册表才收得下。

## 4.1.5 工具该拆多细

注册表有了，下一个问题是：**一个工具的粒度该怎么定？**

假设你要让 Harnex 能改代码，可以只给它一个工具：

```text
apply_patch(path, old, new)   ← 粗：一次改掉你指定的那一处
```

也可以拆成一整套按行操作：

```text
read_line(path, n)           读第 n 行
replace_line(path, n, text)  替换第 n 行
insert_line(path, n, text)   在第 n 行后插入
delete_line(path, n)         删除第 n 行
```

第二种看起来「能力更强、控制更细」，其实是个陷阱。

**按行操作把「找到改哪」交给了模型**：模型要先读文件、数出第几行，再调用 `replace_line(path, 42, ...)`。文件中途变了，或者它数错一行，改的就是别处。工具仍返回成功，模型看不出来。

**按行操作还会把一轮任务拉长**：改三处就要调用三次、来回三次。第 2 章说过：Agent 的延迟大约等于 N 次串行调用模型之和。工具拆得越细，N 越大。

**经验法则：一个工具 = 模型自己能判断成败的一个动作。**

`apply_patch(path, old, new)` 符合这条。模型给出「哪段原文、换成什么」，工具回答三种结果：改成功、没找到这段原文、这段原文出现了多次。看返回就知道成功还是失败。这一步也是一次做完的：要么整处替换，要么文件保持原样。

`replace_line(path, 42, ...)` 不符合。模型给的是「第 42 行」，但它无法确认第 42 行就是要改的那一行。工具说成功，也不等于改对了。

### 粒度怎么选

每一行都是一个判断。左列是「留成一个工具」的信号，右列是「可以拆开」的信号。

| 判断问题 | 粗粒度（留成一个工具） | 细粒度（拆成多个工具） |
| --- | --- | --- |
| 模型能看出这一步是成功还是失败吗？ | 能，例如「替换成功 / 没找到原文」 | — |
| 中间步骤要不要给用户看？ | 不用，用户只关心结果 | 要，做完一步先确认 |
| 拆开之后，模型要猜行号、偏移量吗？ | 要猜。别拆 | 不用猜，每步输入都是明确的 |
| 拆开之后，来回次数会增加多少？ | 明显变多。别拆 | 基本不变 |
| 出错时好不好查？ | 好查：一个动作一个结果 | 难查：要找是哪一步错的 |

最后一行的「难查」是拆开的代价，不是拆开的理由。

**还有一条规则：** 如果中间某一步需要用户点头，那一步就该单独做成工具，或做成审批点（第 15 章）。能留成一个工具，是因为这一步内部没有需要人拍板的地方。

### 反例：把 20 个增删改查接口交给模型

最常见的粒度错误，是把后端接口原封不动交给模型：

```text
create_user / get_user / update_user / delete_user / list_users
create_order / get_order / ... （再乘上其他三个实体，大约 20 个）
```

坏处有两层。

**选择变难。** 工具从几条变成几十条，每次都要塞进上下文。模型要在 20 个名字里挑一个，名字越多，选错越多。

**和用户说的话对不上。** `delete_user` 是数据库层面的动作。用户说的是「把这个离职同事的账号停掉」。模型得自己把这句话翻译成一串接口调用。中间想歪一步，就可能真的删错数据。

正确的做法是：**按任务语义来封装**，而不是按数据库表暴露：

```text
offboard_employee(name)      ← 停用账号、转移文件、发通知，一次做完
```

对模型来说，这仍是一件自己能判断成败的事：只看到一个工具，调用一次，看返回就知道成没成。内部调了几个 API，是你的实现细节，模型不需要知道。
