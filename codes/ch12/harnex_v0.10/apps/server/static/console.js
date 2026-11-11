// harnex/apps/server/static/console.js —— 空窗看门狗：沉默超过阈值就再报一次当前状态
let watchdog = null;      // setTimeout 给的编号，用来取消上一次的闹钟

function armWatchdog(label, seconds) {
  if (watchdog) {
    clearTimeout(watchdog);      // 先撤掉上一次，否则闹钟会叠好几个
  }
  watchdog = setTimeout(function () {
    showStatus(label + "……（已 " + seconds.toFixed(1) + " 秒）");
    armWatchdog(label, seconds + 1);     // 还在沉默，就加一秒再报
  }, 1000);
}

// 每收到一个事件就调它：有动静了，「正在执行…」就该消失
function disarmWatchdog() {
  if (watchdog) {
    clearTimeout(watchdog);
    watchdog = null;
  }
  clearStatus();
}

// 跑起来看到：工具跑着不吭声时，状态条每秒换一次「……已 N 秒」；
// 一有输出进来，disarmWatchdog 被叫一次，这条提示立刻消失。
