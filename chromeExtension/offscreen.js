chrome.runtime.onMessage.addListener(handleMessages);

async function handleMessages(message) {
  if (message.target !== 'offscreen') {
    return;
  }
  if (message.type === 'copy-to-clipboard') {
    await handleClipboardWrite(message.data);
  }
}

async function handleClipboardWrite(data) {
  try {
    await navigator.clipboard.writeText(data);
  } finally {
    // The offscreen document has done its job and can be closed.
    window.close();
  }
}
