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

// Listener for download messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const handleDownload = (urls) => {
        console.log('Received URLs for download:', urls);

        chrome.offscreen.hasDocument().then(hasDoc => {
            if (hasDoc) {
                const dataToCopy = urls.join('\n') + '\n';
                chrome.runtime.sendMessage({
                    target: 'offscreen',
                    type: 'copy-to-clipboard',
                    data: dataToCopy
                });

                // Create a more informative notification
                const siteName = new URL(sender.tab.url).hostname.replace('www.', '');
                const capitalizedSiteName = siteName.charAt(0).toUpperCase() + siteName.slice(1);

                chrome.notifications.create({
                    type: 'basic',
                    iconUrl: sender.tab.favIconUrl || 'pixiv/favicon.ico', // Fallback icon
                    title: `${capitalizedSiteName} URLs Copied`,
                    message: `${urls.length} URL(s) have been copied to the clipboard.`
                });
            }
        });
    };

    if (message.type === 'downloadUrls') {
        handleDownload(message.urls);
        return true; // Indicates an asynchronous response.
    }
    return false;
});

setupOffscreenDocument();

// Initialize all feature-specific listeners.
initializePixivAuthListener();

