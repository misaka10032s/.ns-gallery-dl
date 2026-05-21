import { submitLinks } from '../../core/api.js';

export async function handleDownloadMessage(message, sender) {
  if (message.type === 'downloadUrls') {
    await submitLinks(message.urls || [], { sender, source: 'extension' });
    return true;
  }
  if (message.type === 'submitYtdlp') {
    const urls = [message.url].filter(Boolean);
    await submitLinks(urls, { sender, providerHint: 'ytdlp', source: 'extension' });
    return true;
  }
  return false;
}
