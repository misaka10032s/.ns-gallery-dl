"""
tests/test_auth_failure.py

app.domain.auth_failure.classify() — the three-way (AUTH / NOT_AUTH /
INDETERMINATE) classifier for a download failure's error text (dispatch
item 2, phase 1a). Every signal is checked against REAL error text this app's
job history actually produced (tallied directly against this app's jobs
table) or against the exact wording the installed gallery-dl (1.32.1) /
yt-dlp packages emit for their shared auth-required code paths — never
invented strings.
"""
from __future__ import annotations

import pytest

from app.domain import auth_failure


class TestDefiniteAuth:
    @pytest.mark.parametrize(
        "error",
        [
            # gallery-dl AuthRequired / AuthenticationError / AuthorizationError —
            # job.py logs these as "{ClassName}: {message}" (verified against
            # venv/Lib/site-packages/gallery_dl/job.py).
            "[twitter][error] AuthRequired: Protected Tweet",
            "[pixiv][error] AuthenticationError: Invalid login credentials",
            "[patreon][error] AuthorizationError: Insufficient privileges to access this resource",
            # instagram's own base Extractor.request() redirect-to-login message —
            # a REAL occurrence in this app's job history (4x).
            "[instagram][error] HTTP redirect to login page (https://www.instagram.com/accounts/login/)",
            # HttpError embedding a bare 401 — unambiguous per RFC 7235.
            "[somesite][error] HttpError: '401 Unauthorized' for 'https://somesite.example/x'",
            # yt-dlp's shared InfoExtractor.raise_login_required()/_login_hint() —
            # a REAL occurrence in this app's job history (twitter).
            "ERROR: [twitter] 123: You are not authorized to view this protected tweet. "
            "Use --cookies, --cookies-from-browser, --username and --password, "
            "--netrc-cmd, or --netrc (twitter) to provide account credentials. "
            "See  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp  "
            "for how to manually pass cookies",
        ],
    )
    def test_classifies_auth(self, error):
        assert auth_failure.classify(error) == auth_failure.AUTH


class TestDefiniteNotAuth:
    @pytest.mark.parametrize(
        "error",
        [
            # Reused stale-extractor classifier (app.services.updater_service) —
            # an extractor bug, confidently not a credential problem.
            "[gallery-dl][error] Unable to extract bootstrap data",
            "[danbooru][error] Failed to parse JSON data:  JSONDecodeError: Expecting value",
            # gallery-dl's own ChallengeError (Cloudflare/bot-detection) — a
            # CAPTCHA/challenge wall, not a missing-credential state.
            "[somesite][error] ChallengeError: interactive challenge (403 Forbidden) for 'https://somesite.example/x'",
            "[instagram][error] HTTP redirect to challenge page (https://www.instagram.com/challenge/)",
            # Plain 404 / 5xx.
            "[danbooru][error] HttpError: '404 Not Found' for 'https://danbooru.donmai.us/posts/1.json'",
            "[somesite][error] HttpError: '503 Service Unavailable' for 'https://somesite.example/x'",
            # Network/timeout shapes.
            "ConnectionError: Max retries exceeded with url: /dl/abc",
            "requests.exceptions.ConnectTimeout: HTTPSConnectionPool(host='x', port=443): Read timed out.",
        ],
    )
    def test_classifies_not_auth(self, error):
        assert auth_failure.classify(error) == auth_failure.NOT_AUTH


class TestIndeterminate:
    @pytest.mark.parametrize(
        "error",
        [
            # NotFoundError — genuinely ambiguous (deleted vs. hidden-without-
            # login); a REAL occurrence in this app's job history (pixiv, 11x).
            "[pixiv][error] NotFoundError: Requested resource (gallery/image) could not be found",
            # Bare 403 with no Auth* class name — ambiguous vs. a bot block.
            "[somesite][error] HttpError: '403 Forbidden' for 'https://somesite.example/x'",
            # gallery-dl's AbortExtraction bare-quoted fallback — a REAL
            # occurrence in this app's job history (twitter, 60x). Confirmed
            # source: gallery_dl/extractor/twitter.py's
            # `raise self.exc.AbortExtraction(f"'{tweet.get('reason') or 'Unavailable'}'")`
            # — logged bare (no class prefix) per job.py's AbortExtraction
            # branch, and carries no signal at all when `reason` is absent.
            "[twitter][error] 'Unavailable'",
            # Never-seen-before message (simulates a brand-new site or an
            # engine-version wording change) — must default safely, never a
            # forced guess.
            "[somesite][error] Something went wrong in a way this classifier has never heard of",
        ],
    )
    def test_classifies_indeterminate(self, error):
        assert auth_failure.classify(error) == auth_failure.INDETERMINATE

    def test_empty_string_is_indeterminate(self):
        assert auth_failure.classify("") == auth_failure.INDETERMINATE

    def test_none_is_indeterminate(self):
        assert auth_failure.classify(None) == auth_failure.INDETERMINATE
