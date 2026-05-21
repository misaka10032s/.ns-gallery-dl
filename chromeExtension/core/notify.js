export function notify({ title, message, iconUrl = 'pixiv/favicon.ico' }) {
  chrome.notifications.create({
    type: 'basic',
    iconUrl,
    title,
    message,
  });
}
