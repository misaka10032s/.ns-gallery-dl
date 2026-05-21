import { sendOffscreenMessage } from '../background/offscreen.js';
import { notify } from './notify.js';

export const API_BASE = 'http://127.0.0.1:7601';

async function copyFallback(urls, sender) {
  const text = `${urls.join('\n')}\n`;
  await sendOffscreenMessage({
    type: 'copy-to-clipboard',
    data: text,
  });
  const hostname = sender?.tab?.url ? new URL(sender.tab.url).hostname.replace('www.', '') : 'Links';
  notify({
    title: `${hostname} URLs Copied`,
    message: `${urls.length} URL(s) copied to the clipboard.`,
    iconUrl: sender?.tab?.favIconUrl || 'pixiv/favicon.ico',
  });
}

export async function submitLinks(urls, { sender, providerHint = null, source = 'extension' } = {}) {
  try {
    const response = await fetch(`${API_BASE}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ links: urls, providerHint, source }),
    });
    if (!response.ok) {
      throw new Error('Local server responded with an error.');
    }
    const result = await response.json();
    notify({
      title: 'Links Sent to NS Media Hub',
      message: result.message || `${urls.length} URL(s) queued successfully.`,
      iconUrl: sender?.tab?.favIconUrl || 'pixiv/favicon.ico',
    });
    return true;
  } catch (error) {
    console.warn('Could not connect to local server; falling back to clipboard.', error);
    await copyFallback(urls, sender);
    return false;
  }
}

export async function fetchDashboardSummary() {
  const response = await fetch(`${API_BASE}/api/dashboard`);
  if (!response.ok) {
    throw new Error('Local server responded with an error.');
  }
  return response.json();
}
