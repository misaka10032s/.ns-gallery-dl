const OFFSCREEN_DOCUMENT_PATH = 'offscreen.html';
let creating;

export async function ensureOffscreenDocument() {
  if (await chrome.offscreen.hasDocument()) {
    return;
  }
  if (creating) {
    await creating;
    return;
  }
  creating = chrome.offscreen.createDocument({
    url: OFFSCREEN_DOCUMENT_PATH,
    reasons: [chrome.offscreen.Reason.CLIPBOARD],
    justification: 'Clipboard access for auth tokens and API fallback export.',
  });
  try {
    await creating;
  } finally {
    creating = null;
  }
}

export async function sendOffscreenMessage(message) {
  await ensureOffscreenDocument();
  return chrome.runtime.sendMessage({
    target: 'offscreen',
    ...message,
  });
}
