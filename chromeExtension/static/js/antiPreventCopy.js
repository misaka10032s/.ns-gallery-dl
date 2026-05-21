// 移除所有元素的選取、右鍵選單、滑鼠按下、複製、剪下和貼上事件
document.querySelectorAll('*').forEach(e => {
  e.onselectstart = null; // 解除選取事件
  e.oncontextmenu = null; // 解除右鍵選單事件
  e.onmousedown = null; // 解除滑鼠按下事件
  e.oncopy = null; // 解除複製事件
  e.oncut = null; // 解除剪下事件
  e.onpaste = null; // 解除貼上事件
});

// 若有額外的事件綁定，使用事件委派解除所有的 copy 和 paste 事件
document.addEventListener('copy', (event) => event.stopImmediatePropagation(), true);
document.addEventListener('paste', (event) => event.stopImmediatePropagation(), true);