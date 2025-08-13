// offscreen.js

// Listen for the data payload from the background script.
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'copy-this') {
    copyToClipboard(message.data);
  }
});

// Signal to the background script that the offscreen document is ready.
chrome.runtime.sendMessage({ type: 'offscreen-ready' });

// The actual clipboard write function.
async function copyToClipboard(data) {
  try {
    await navigator.clipboard.writeText(data);
  } finally {
    // Close the offscreen document after the operation is complete.
    window.close();
  }
}
