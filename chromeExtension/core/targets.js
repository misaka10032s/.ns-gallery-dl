const SHORTCUT_PATTERNS = [
  { pattern: /^pw(\d+)$/i, expand: (id) => `https://www.pixiv.net/artworks/${id}` },
  { pattern: /^pu(\d+)$/i, expand: (id) => `https://www.pixiv.net/users/${id}` },
  { pattern: /^p(\d+)$/i, expand: (id) => `https://www.pixiv.net/artworks/${id}` },
  { pattern: /^n(\d+)$/i, expand: (id) => `https://nhentai.net/g/${id}/` },
  { pattern: /^w(\d+)$/i, expand: (id) => `https://www.wnacg.com/photos-index-aid-${id}.html` },
];

const SITE_ACTIONS = [
  {
    match: /(^|\.)youtube\.com$|(^|\.)youtu\.be$/i,
    label: '下載此影片',
    providerHint: 'ytdlp',
  },
  {
    match: /(^|\.)x\.com$|(^|\.)twitter\.com$/i,
    label: '下載此貼文',
    providerHint: 'ytdlp',
  },
  {
    match: /(^|\.)facebook\.com$|(^|\.)fb\.watch$/i,
    label: '下載此內容',
    providerHint: 'ytdlp',
  },
  {
    match: /(^|\.)pixiv\.net$/i,
    label: '下載此作品',
    providerHint: 'gallery-dl',
  },
  {
    match: /(^|\.)nhentai\.net$/i,
    label: '下載此本子',
    providerHint: 'gallery-dl',
  },
  {
    match: /(^|\.)wnacg\.com$/i,
    label: '下載此作品',
    providerHint: 'gallery-dl',
  },
  {
    match: /(^|\.)yande\.re$/i,
    label: '下載此頁面',
    providerHint: 'gallery-dl',
  },
];

function normalizeHost(hostname = '') {
  return hostname.replace(/^www\./i, '').replace(/^m\./i, '').toLowerCase();
}

function stripWrapper(value) {
  return value.replace(/^[<>"'`([{【「『]+|[>)"'`}\]】」』.,!?;:]+$/g, '');
}

function repairObfuscation(value) {
  return value
    .replace(/hxxps:\/\//gi, 'https://')
    .replace(/hxxp:\/\//gi, 'http://')
    .replace(/\(\s*dot\s*\)|\[\s*dot\s*\]|\{\s*dot\s*\}/gi, '.')
    .replace(/\(\s*\.\s*\)|\[\s*\.\s*\]|\{\s*\.\s*\}/g, '.')
    .replace(/\s*\.\s*/g, '.')
    .replace(/[.]{2,}/g, '.')
    .trim();
}

function expandShortcut(value) {
  if (value.toLowerCase() === 'x') {
    return 'https://x.com';
  }

  for (const entry of SHORTCUT_PATTERNS) {
    const match = value.match(entry.pattern);
    if (match) {
      return entry.expand(match[1]);
    }
  }
  return value;
}

function addSchemeIfMissing(value) {
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value) || value.startsWith('ytdlp://')) {
    return value;
  }
  if (/^[a-z0-9.-]+\.[a-z]{2,}(?:\/.*)?$/i.test(value)) {
    return `https://${value}`;
  }
  return value;
}

export function normalizeDownloadTargets(rawText) {
  const text = String(rawText ?? '').trim();
  if (!text) return [];

  const normalized = text
    .replace(/\r/g, '\n')
    .replace(/[,\u3000\t]+/g, '\n')
    .replace(/\s+/g, '\n');

  const tokens = normalized
    .split('\n')
    .map((item) => stripWrapper(repairObfuscation(item)))
    .filter(Boolean)
    .map(expandShortcut)
    .map(addSchemeIfMissing)
    .filter((item) => item && (/^[a-z][a-z0-9+.-]*:\/\//i.test(item) || /^https?:\/\/?/i.test(item)));

  return Array.from(new Set(tokens));
}

export function getSiteAction(url) {
  try {
    const host = normalizeHost(new URL(url).hostname);
    return SITE_ACTIONS.find((item) => item.match.test(host)) ?? null;
  } catch {
    return null;
  }
}

export function inferProviderHint(url) {
  return getSiteAction(url)?.providerHint ?? null;
}
