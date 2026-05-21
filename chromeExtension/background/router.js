import { handleDownloadMessage } from '../features/download_submit/submit.js';

export function registerMessageRouter() {
  chrome.runtime.onMessage.addListener((message, sender) => {
    const handle = async () => handleDownloadMessage(message, sender);
    if (message.type === 'downloadUrls' || message.type === 'submitYtdlp') {
      handle();
      return true;
    }
    return false;
  });
}
