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

  // 2. Copy the code to the clipboard using the offscreen document.
  copyTextToClipboard(code);
}

// This function sends a message to the background script to copy text.
async function copyTextToClipboard(text) {
  await chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'copy-to-clipboard',
    data: text,
  });
}
