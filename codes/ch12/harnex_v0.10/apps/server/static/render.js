// harnex/apps/server/static/render.js —— 事件到组件：一张表就够了，没有第十种东西
// 右边那些 renderXxx 都在本文件里，各画各的一块。这张表只是「类型 → 画法」的对照。
const RENDERERS = {
  user_message:     renderUser,
  assistant_delta:  renderDelta,
  tool_start:       renderToolStart,
  tool_output:      renderToolLine,
  tool_result:      renderToolResult,
  todo_update:      renderTodos,
  approval_request: renderApproval,
  approval_denied:  renderDenied,
  turn_done:        renderTurnDone,
};

function render(event) {
  const handler = RENDERERS[event.type];
  if (!handler) {
    // 内核加了新事件、界面还没跟上：记一笔，别让整屏崩掉
    console.warn("不认识的事件", event.type);
    return;
  }
  handler(event);
}

// 跑起来看到：控制台一条警告都没有，说明九个事件都被这张表接住了。
// 哪天内核多出一个事件，这里会立刻报出它的名字——这就是这张表的用处。
