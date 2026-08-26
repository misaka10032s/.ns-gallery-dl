// QR / barcode decode helper for the "解析QRcode" context-menu action (module/script.js deQrcode).
// Wraps the vendored ZXingWASM reader (ZxingReader.js, from zxing-wasm@1.3.5 dist/iife/reader) with
// a bounded preprocessing ladder so small/rotated/low-contrast codes get more than one attempt.
//
// Environment-agnostic on purpose: this file is injected as-is into the extension's content-script
// isolated world (browser), and also loaded verbatim by the Node test harness under
// chromeExtension/test/ (see docs/superpowers/tests/ for the report) so the exact same decode logic
// is what gets measured. It never touches `document`/`canvas` itself — the caller (browser: script.js
// deQrcode; Node: the test harness) is responsible for turning a source image into a plain
// { data: Uint8ClampedArray, width, height } pixel buffer (the same shape as CanvasRenderingContext2D
// .getImageData()'s return value — ZXingWASM.readBarcodesFromImageData() only reads those 3 fields).
(function (global) {
    "use strict";

    // Bounded attempt budget (HARD CAP = 6): each ladder stage is exactly one decode call, tried in
    // order, stopping at the first hit. A hopeless image (no code, or one the decoder can never read)
    // still only costs 6 WASM decode calls — each call is O(10-50ms) on a typical context-menu-sized
    // image, so the worst case is well under ~500ms, not a UI hang.
    const LADDER = [
        { name: "raw", transform: (img) => img },
        { name: "greyscale-contrast", transform: toGreyscaleContrast },
        { name: "upscale-2x", transform: (img) => upscale(img, 2) },
        { name: "rotate-90", transform: (img) => rotate(img, 90) },
        { name: "rotate-180", transform: (img) => rotate(img, 180) },
        { name: "rotate-270", transform: (img) => rotate(img, 270) },
    ];

    let zxingReadyPromise = null;

    // Lazily configure + warm up the wasm module exactly once per page/process.
    // Browser: fetch the vendored .wasm via the extension's own resource URL (web_accessible_resources
    // in manifest.json — never a CDN, matches the existing QrcodeDecoder.js vendoring convention).
    // Node test harness: the caller preloads the raw wasm bytes into global.__ZXING_WASM_BYTES__, which
    // skips fetch/URL resolution entirely (see zxing-wasm's own `wasmBinary` override — Ft()/Ot() in
    // the vendored bundle return the supplied bytes directly instead of calling fetch()).
    function ensureZxingReady() {
        if (zxingReadyPromise) return zxingReadyPromise;
        zxingReadyPromise = (async () => {
            const ZXingWASM = global.ZXingWASM;
            if (!ZXingWASM) throw new Error("ZXingWASM is not loaded (ZxingReader.js must be injected first)");
            if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL) {
                ZXingWASM.setZXingModuleOverrides({
                    locateFile: (fileName) => chrome.runtime.getURL("static/js/" + fileName),
                });
            } else if (global.__ZXING_WASM_BYTES__) {
                ZXingWASM.setZXingModuleOverrides({ wasmBinary: global.__ZXING_WASM_BYTES__ });
            }
            await ZXingWASM.getZXingModule();
        })();
        return zxingReadyPromise;
    }

    // Luminance greyscale + min/max contrast stretch. Cheap, no external deps.
    function toGreyscaleContrast(img) {
        const { data, width, height } = img;
        const n = width * height;
        const lum = new Float32Array(n);
        let min = 255, max = 0;
        for (let i = 0; i < n; i++) {
            const o = i * 4;
            const l = 0.299 * data[o] + 0.587 * data[o + 1] + 0.114 * data[o + 2];
            lum[i] = l;
            if (l < min) min = l;
            if (l > max) max = l;
        }
        const range = Math.max(1, max - min);
        const out = new Uint8ClampedArray(data.length);
        for (let i = 0; i < n; i++) {
            const o = i * 4;
            const v = Math.round(((lum[i] - min) / range) * 255);
            out[o] = out[o + 1] = out[o + 2] = v;
            out[o + 3] = data[o + 3];
        }
        return { data: out, width, height };
    }

    // Nearest-neighbor upscale — decoders are weak on small (e.g. ~80px) codes.
    function upscale(img, factor) {
        const { data, width, height } = img;
        const nw = width * factor, nh = height * factor;
        const out = new Uint8ClampedArray(nw * nh * 4);
        for (let y = 0; y < nh; y++) {
            const sy = Math.min(height - 1, Math.floor(y / factor));
            for (let x = 0; x < nw; x++) {
                const sx = Math.min(width - 1, Math.floor(x / factor));
                const so = (sy * width + sx) * 4;
                const dOff = (y * nw + x) * 4;
                out[dOff] = data[so]; out[dOff + 1] = data[so + 1];
                out[dOff + 2] = data[so + 2]; out[dOff + 3] = data[so + 3];
            }
        }
        return { data: out, width: nw, height: nh };
    }

    // 90/180/270 rotation via index remap — no canvas needed, so this stays pure-JS and testable in Node.
    function rotate(img, degrees) {
        const { data, width, height } = img;
        if (degrees === 180) {
            const n = width * height;
            const out = new Uint8ClampedArray(data.length);
            for (let i = 0; i < n; i++) {
                const so = i * 4, dOff = (n - 1 - i) * 4;
                out[dOff] = data[so]; out[dOff + 1] = data[so + 1];
                out[dOff + 2] = data[so + 2]; out[dOff + 3] = data[so + 3];
            }
            return { data: out, width, height };
        }
        const nw = height, nh = width;
        const out = new Uint8ClampedArray(nw * nh * 4);
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const so = (y * width + x) * 4;
                let dx, dy;
                if (degrees === 90) { dx = height - 1 - y; dy = x; }
                else { dx = y; dy = width - 1 - x; } // 270
                const dOff = (dy * nw + dx) * 4;
                out[dOff] = data[so]; out[dOff + 1] = data[so + 1];
                out[dOff + 2] = data[so + 2]; out[dOff + 3] = data[so + 3];
            }
        }
        return { data: out, width: nw, height: nh };
    }

    // Returns:
    //   { text, format, stage } on success
    //   null                    if the ladder ran to completion and genuinely found nothing
    //   throws                  only if EVERY stage's decode call itself errored (wasm/runtime failure) —
    //                           this is what lets the caller tell "no code" apart from "decoder broke".
    async function decodeQrOrBarcode(imageData, options) {
        await ensureZxingReady();
        const opts = Object.assign({ tryHarder: true, formats: [] }, options);
        let anyStageRan = false;
        let lastError = null;
        for (const stage of LADDER) {
            try {
                const variant = stage.transform(imageData);
                const results = await global.ZXingWASM.readBarcodesFromImageData(variant, opts);
                anyStageRan = true;
                if (results && results.length > 0 && results[0].text) {
                    return { text: results[0].text, format: results[0].format, stage: stage.name };
                }
            } catch (e) {
                lastError = e;
            }
        }
        if (!anyStageRan && lastError) throw lastError;
        return null;
    }

    global.decodeQrOrBarcode = decodeQrOrBarcode;
    // exposed for the Node test harness only (introspection / picking stage names in the report table)
    global.__qrBarcodeLadderStageNames = LADDER.map((s) => s.name);
})(typeof window !== "undefined" ? window : globalThis);
