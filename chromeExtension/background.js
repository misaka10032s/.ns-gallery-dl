// chromeExtension/background.js
import { initializePixivAuthListener } from './pixiv/auth.js';

// Initialize all feature-specific listeners.
// The auth listener is now self-contained and handles all its own logic.
initializePixivAuthListener();