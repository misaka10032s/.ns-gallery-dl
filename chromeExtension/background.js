// chromeExtension/background.js
import { initializePixivAuthListener } from './pixiv/auth.js';

const OFFSCREEN_DOCUMENT_PATH = 'offscreen.html';

// A global promise to ensure the offscreen document is created only once.
let creating;

// Function to create and manage the offscreen document.
async function setupOffscreenDocument() {
  if (await chrome.offscreen.hasDocument()) {
    return;
  }

  if (creating) {
    await creating;
  } else {
    creating = chrome.offscreen.createDocument({
      url: OFFSCREEN_DOCUMENT_PATH,
      reasons: [chrome.offscreen.Reason.CLIPBOARD],
      justification: 'Clipboard access for auth tokens.',
    });
    await creating;
    creating = null;
  }
}

setupOffscreenDocument();

// Initialize all feature-specific listeners.
initializePixivAuthListener();
