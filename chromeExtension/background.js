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

async function handleAuthCode(code) {
  await createOffscreenDocument();
  chrome.runtime.sendMessage({
    type: 'copy-to-clipboard',
    target: 'offscreen',
    data: code,
  });
  showNotification(code);
}

function showNotification(code) {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icon48.png', // You'll need to add an icon file for this to work
    title: 'Pixiv Auth Code Captured',
    message: `The code has been copied to your clipboard: ${code.substring(0, 10)}...`,
    priority: 2,
  });
}

let creating;
async function createOffscreenDocument() {
  if (await chrome.offscreen.hasDocument()) {
    return;
  }
  if (creating) {
    await creating;
  } else {
    creating = chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: [chrome.offscreen.Reason.CLIPBOARD],
      justification: 'Need to copy the auth code to the clipboard.',
    });
    await creating;
    creating = null;
  }
}
