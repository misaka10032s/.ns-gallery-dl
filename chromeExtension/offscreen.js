// chromeExtension/offscreen.js

// This script is designed to run in an offscreen document.
// It handles copying text to the clipboard.

chrome.runtime.onMessage.addListener(async (message) => {
  if (message.target !== 'offscreen') {
    return;
  }

  if (message.type === 'copy-to-clipboard') {
    await handleCopyToClipboard(message.data);
  }
});

async function handleCopyToClipboard(text) {
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    console.log('Text copied to clipboard:', text);

    // this will cause document was not focused
    // await navigator.clipboard.writeText(text);
  } catch (error) {
    console.error('Failed to copy text to clipboard:', error);
  }
}
