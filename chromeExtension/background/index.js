import { ensureOffscreenDocument } from './offscreen.js';
import { registerMessageRouter } from './router.js';
import '../NStools_background.js';
import { initializePixivAuthListener } from '../pixiv/auth.js';

ensureOffscreenDocument().catch((error) => {
  console.error('Failed to initialize offscreen document.', error);
});
registerMessageRouter();
initializePixivAuthListener();
