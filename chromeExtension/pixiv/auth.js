// chromeExtension/pixiv/auth.js

// This function sets up the listener for the Pixiv OAuth callback.
export function initializePixivAuthListener() {
  const PIXIV_CALLBACK_URL = 'https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback';

  chrome.webRequest.onBeforeRequest.addListener(
    (details) => {
      if (details.url.startsWith(PIXIV_CALLBACK_URL)) {
        const url = new URL(details.url);
        const authCode = url.searchParams.get('code');
        if (authCode) {
          handleAuthCode(authCode);
        }
      }
    },
    { urls: ["https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback*"] }
  );
}

function handleAuthCode(code) {
  // 1. Fire the notification directly.
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'pixiv/favicon.ico',
    title: 'Pixiv Auth Code Captured',
    message: `The code has been copied to your clipboard: ${code.substring(0, 10)}...`,
    priority: 2,
  });

  // 2. Copy the code to the clipboard using scripting.
  copyTextToClipboard(code);
}

async function copyTextToClipboard(text) {
  try {
    // Find the active tab to inject the script into.
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    console.log('Text copied to clipboard:', text, tab);

    if (tab) {
      // insert text to body
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (textToCopy) => {
          console.log('Text copied to clipboard:', textToCopy, navigator, navigator?.clipboard, navigator?.clipboard?.writeText);
          navigator.clipboard.writeText(textToCopy);
        },
        args: [text],
      });
    }
  } catch (err) {
    console.error('Failed to copy text using scripting:', err);
  }
}
