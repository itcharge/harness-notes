// harnex/apps/server/static/paint.js —— 两处性能：一帧画一次，只画看得见的
// 依赖 render.js 里的 render()：这里只管「什么时候画」，不管「怎么画」
let queued = [];          // 排着队、等这一帧画的事件
let scheduled = false;    // 这一帧的活是不是已经排上了

function schedule(event) {
  queued.push(event);
  if (scheduled) {
    return;               // 已经排过一帧，这一帧不再排第二次
  }
  scheduled = true;
  requestAnimationFrame(function () {    // 浏览器画下一帧之前会叫我们一次
    scheduled = false;
    const batch = queued;
    queued = [];
    batch.forEach(render);               // 一帧内来多少条，都在这里画完
  });
}

function visibleRange(scroller, rowHeight) {
  const top = scroller.scrollTop;
  const height = scroller.clientHeight;
  const first = Math.max(0, Math.floor(top / rowHeight) - 20);   // 上面多留 20 行
  const last = Math.ceil((top + height) / rowHeight) + 20;       // 下面也多留 20 行
  return [first, last];
}

// 跑起来看到：模型吐字时页面不再一跳一跳，输入框里的字也不会被顶走；
// 三千条的会话一次 DOM 只建十几行，滚动条长度照旧对得上。
