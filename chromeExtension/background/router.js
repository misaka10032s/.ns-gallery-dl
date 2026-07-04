import { handleDownloadMessage } from '../features/download_submit/submit.js';

export function registerMessageRouter() {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'downloadUrls' || message.type === 'submitYtdlp' || message.type === 'downloadImageSelection') {
      // Respond with { success: true/false } so content scripts can auto-clear
      // selection on successful submit (spec §D / selection-mode-v2).
      handleDownloadMessage(message, sender)
        .then((success) => { sendResponse({ success: !!success }); })
        .catch(() => { sendResponse({ success: false }); });
      return true; // keep message channel open for async sendResponse
    }
    return false;
  });
}
