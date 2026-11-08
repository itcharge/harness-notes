// harnex/apps/server/static/card.js —— 工具卡片：三个状态，耗时从事件到达时起算
// timeline 是页面上那条时间线，整页只有一个（11.5 建的）
function openCard(event) {
  const card = document.createElement("div");
  card.className = "card running";
  card.dataset.id = event.tool_call_id;
  card.dataset.group = event.group || "";
  card.dataset.since = String(Date.now());   // 起算点：事件到达这一刻，不用模型自报

  const title = document.createElement("span");
  title.className = "name";
  title.textContent = event.name;            // 外部内容一律 textContent，不拼 HTML
  card.append(title);
  timeline.append(card);
  return card;
}

// 跑起来看到：时间线上多出一张卡片，标题是工具名——名字来自事件，不是模型嘴上说的。
// 卡片一开始带 running（黄），收到 tool_result 之后由另一个函数改成 ok 或 fail。
