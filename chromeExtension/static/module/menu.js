import { reloadImage, anitWhite, navigation, searchSaucenao, searchAscii2d, searchSoutubot, searchTraceMoe, getBahaImg, exportChatGPTConversation, deQrcode, getPixivAllImg, openBackgroundImageInNewTab } from "./script.js";
import { useUtils } from "./utils.js";
import { executeScript, getDomain, executeStoreScript, injectScript, downloadImages } from "./core.js";
import { tabVars, storeData } from "./store.js";
import key from "../secret/key.js";
import { submitLinks } from "../../core/api.js";
import { getSiteAction, inferProviderHint, normalizeDownloadTargets } from "../../core/targets.js";

async function submitCurrentTarget(target, { tab, providerHint = null } = {}) {
    const targets = normalizeDownloadTargets(target);
    if (!targets.length) return;
    const hint = providerHint ?? (targets.length === 1 ? inferProviderHint(targets[0]) : null);
    await submitLinks(targets, {
        sender: { tab },
        providerHint: hint,
        source: "extension",
    });
}

// ########################################################
// #                                                      #
// #                     context menu                     #
// #                                                      #
// ########################################################
export const contextMenus = {
    downloadRoot: {
        title: "NS Media Hub",
        contexts: ["page", "selection", "link"],
    },
    downloadSelection: {
        parentId: "downloadRoot",
        title: "下載: %s",
        contexts: ["selection"],
        script: async (info, tab) => {
            await submitCurrentTarget(info.selectionText, { tab });
        }
    },
    downloadLink: {
        parentId: "downloadRoot",
        title: "下載此連結",
        contexts: ["link"],
        script: async (info, tab) => {
            await submitCurrentTarget(info.linkUrl, { tab });
        }
    },
    downloadYoutubePage: {
        parentId: "downloadRoot",
        title: "下載此影片",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "ytdlp" });
        },
        documentUrlPatterns: ["https://www.youtube.com/*", "https://youtu.be/*"]
    },
    downloadXPage: {
        parentId: "downloadRoot",
        title: "下載此貼文",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab });
        },
        documentUrlPatterns: ["https://x.com/*", "https://twitter.com/*"]
    },
    downloadFacebookPage: {
        parentId: "downloadRoot",
        title: "下載此內容",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "ytdlp" });
        },
        documentUrlPatterns: ["https://www.facebook.com/*", "https://fb.watch/*"]
    },
    downloadPixivPage: {
        parentId: "downloadRoot",
        title: "下載此作品",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "gallery-dl" });
        },
        documentUrlPatterns: ["https://www.pixiv.net/users/*", "https://www.pixiv.net/artworks/*"]
    },
    downloadNhentaiPage: {
        parentId: "downloadRoot",
        title: "下載此本子",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "gallery-dl" });
        },
        documentUrlPatterns: ["https://nhentai.net/*"]
    },
    downloadWnacgPage: {
        parentId: "downloadRoot",
        title: "下載此作品",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "gallery-dl" });
        },
        documentUrlPatterns: ["https://wnacg.com/*", "https://www.wnacg.com/*"]
    },
    downloadYanderePage: {
        parentId: "downloadRoot",
        title: "下載此頁面",
        contexts: ["page"],
        script: async (info, tab) => {
            await submitCurrentTarget(tab.url, { tab, providerHint: "gallery-dl" });
        },
        documentUrlPatterns: ["https://yande.re/post", "https://yande.re/post?tags=*"]
    },
    openPopup: {
        title: "開啟插件",
        contexts: ["page"],
        script: async (info, tab) => {
            chrome.windows.create({
                type: "popup",
                url: chrome.runtime.getURL("static/template/console/console.html"),
                width: 600,
                height: 400
            });
        }
    },
    reloadImage: {
        title: "重載失敗圖片",
        contexts: ["page"],
        script: async (info, tab) => {
            await executeScript(tab.id, reloadImage);
        }
    },
    anitWhite: {
        title: "解除反白限制",
        contexts: ["page"],
        script: async (info, tab) => {
            await executeScript(tab.id, anitWhite);
        }
    },
    dlsiteASMR: {
        title: "試聽 dlsite ASMR",
        contexts: ["page"],
        script: async (info, tab) => {
            // get url (https://www.dlsite.com/maniax/work/=/product_id/RJxxxxx.html)
            const url = tab.url;
            // get product_id
            const product_id = url.match(/product_id\/RJ(\d+)/);
            // if product_id is not found, return
            if (!product_id) return;
            // go to https://www.asmr.one/work/RJxxxxx
            await chrome.tabs.create({
                url: `https://www.asmr.one/work/RJ${ product_id[1] }`,
                index: tab.index + 1
            });
        },
        documentUrlPatterns: ["https://www.dlsite.com/maniax/work/*"]
    },
    navigation: {
        title: "NWP: %s",
        contexts: ["selection"],
        script: async (info, tab) => {
            await executeScript(tab.id, navigation, info.selectionText);
        }
    },
    textNhentai: {
        title: "使用 N-hentai搜尋: %s",
        contexts: ["selection"],
        script: async (info, tab) => {
            await chrome.tabs.create({
                url: `http://nhentai.net/search/?q=${ info.selectionText }`,
                // url: `http://nhentai.website/search/?q=${ info.selectionText }`,
                index: tab.index + 1
            });
        }
    },
    textWnacg: {
        title: "使用 Wnacg搜尋: %s",
        contexts: ["selection"],
        script: async (info, tab) => {
            await chrome.tabs.create({
                url: `http://wnacg.com/search/?q=${ info.selectionText }`,
                index: tab.index + 1
            });
        }
    },
    textRemoveWhite: {
        title: "前往: %s",
        contexts: ["selection"],
        script: async (info, tab) => {
            const rmw = info.selectionText
                .replace(/[\s]*/g, "") // replace all whitespace
                .replace(/[\.]{2,}/g, ".") // replace multiple dots with single dot
                .replace(/\(\s*\.\s*\)/, "."); // replace "( . )" with dot, for cases like "example( . )com"
            const target = rmw.match(/^https?:\/\//) ? rmw : `https://${ rmw }`;
            await chrome.tabs.create({
                url: target,
                index: tab.index + 1
            });
        }
    },
    imageSaucenao: {
        title: "使用 saucenao搜尋圖片", // https://saucenao.com
        contexts: ["image"],
        script: async (info, tab) => {
            const isLink = info.srcUrl.startsWith("https:");

            await executeScript(tab.id, useUtils, true);
            const base64 = isLink ? info.srcUrl : (await executeScript(tab.id, searchSaucenao.img2Base64, info.srcUrl))[0].result;
            const newTab = await chrome.tabs.create({
                url: "https://saucenao.com/",
                index: tab.index + 1
            });
            await executeScript(newTab.id, useUtils, true);
            await executeScript(newTab.id, isLink ? searchSaucenao.addUrl : searchSaucenao.addBlob, base64);
        }
    },
    imageAscii2d: {
        title: "使用 ascii2d搜尋圖片", // https://ascii2d.net
        contexts: ["image"],
        script: async (info, tab) => {
            const isLink = info.srcUrl.startsWith("https:");

            await executeScript(tab.id, useUtils, true);
            const base64 = isLink ? info.srcUrl : (await executeScript(tab.id, searchAscii2d.img2Base64, info.srcUrl))[0].result;
            const newTab = await chrome.tabs.create({
                url: "https://ascii2d.net/",
                index: tab.index + 1
            });
            await executeScript(newTab.id, useUtils, true);
            await executeScript(newTab.id, isLink ? searchAscii2d.addUrl : searchAscii2d.addBlob, base64);
        }
    },
    imageSoutubot: {
        title: "使用 soutubot搜尋圖片", // https://soutubot.moe/
        contexts: ["image"],
        script: async (info, tab) => {
            await executeScript(tab.id, useUtils, true);
            const base64 = (await executeScript(tab.id, searchSoutubot.img2Base64, info.srcUrl))[0].result;
            const newTab = await chrome.tabs.create({
                url: "https://soutubot.moe/",
                index: tab.index + 1
            });
            await executeScript(newTab.id, useUtils, true);
            await executeScript(newTab.id, searchSoutubot.addBlob, base64);
        }
    },
    imageTraceMoe: {
        title: "使用 trace.moe找片名", // https://trace.moe
        contexts: ["image"],
        script: async (info, tab) => {
            const isLink = info.srcUrl.startsWith("https:");

            await executeScript(tab.id, useUtils, true);
            const base64 = isLink ? info.srcUrl : (await executeScript(tab.id, searchTraceMoe.img2Base64, info.srcUrl))[0].result;
            const newTab = await chrome.tabs.create({
                url: "https://trace.moe/",
                index: tab.index + 1
            });
            await executeScript(newTab.id, useUtils, true);
            await executeScript(newTab.id, isLink ? searchTraceMoe.addUrl : searchTraceMoe.addBlob, base64);
        }
    },
    getBahaImg: {
        title: "取得巴哈姆特圖片",
        contexts: ["page"],
        script: async (info, tab) => {
            await executeScript(tab.id, getBahaImg, tab);
        },
        documentUrlPatterns: ["https://forum.gamer.com.tw/*"]
    },
    downloadBahaImg: {
        title: "下載巴哈姆特圖片",
        contexts: ["page"],
        script: async (info, tab) => {
            const urlsObjects = (await executeScript(tab.id, getBahaImg, tab, 2))[0].result;
            const newTab = await chrome.tabs.create({
                url: urlsObjects[0].url,
                index: tab.index + 1
            });
            const { downloadMultipleImgs } = useUtils();
            await executeScript(newTab.id, downloadMultipleImgs, tab, urlsObjects);
            // close the opened tab
            newTab && chrome.tabs.remove(newTab.id);
        },
        documentUrlPatterns: ["https://forum.gamer.com.tw/*"]
    },
    exportChatGPTConversation: {
        title: "匯出chatGPT圖片",
        contexts: ["page"],
        script: async (info, tab) => {
            await injectScript(tab.id, "html2canvas.js");
            await executeScript(tab.id, exportChatGPTConversation, tab);
        },
        documentUrlPatterns: ["https://chat.openai.com/*", "https://chatgpt.com/*"]
    },
    deQrcode: {
        title: "解析QRcode",
        contexts: ["image"],
        script: async (info, tab) => {
            await injectScript(tab.id, "QrcodeDecoder.js");
            await executeScript(tab.id, deQrcode, tab);
        }
    },
    getPixivAllImg: {
        title: "pixiv: 下載所有圖片",
        contexts: ["page"],
        script: async (info, tab) => {
            const urlsObjects = (await executeScript(tab.id, getPixivAllImg, info))[0].result;
            const newTab = await chrome.tabs.create({
                url: urlsObjects[0].url,
                 index: tab.index + 1
            });
            const { downloadMultipleImgs } = useUtils();
            await executeScript(newTab.id, downloadMultipleImgs, tab, urlsObjects);
            // close the opened tab
            newTab && chrome.tabs.remove(newTab.id);
        },
        documentUrlPatterns: ["https://www.pixiv.net/artworks/*"]
    },
    removeR18imgiopenmall: {
        title: "移除R18遮擋圖",
        contexts: ["page"],
        script: async (info, tab) => {
            await executeScript(tab.id, async (info, tab) => {
                [...document.querySelectorAll(".img_eighteen_only")].forEach(x => x.remove());
            });
        },
        documentUrlPatterns: ["https://mall.iopenmall.tw/*", "https://www.iopenmall.com/*"]
    },
    openBackgroundImageInNewTab: {
        title: "在新分頁開啟背景圖片",
        contexts: ["all"],
        script: async (info, tab) => {
            const url = (await executeScript(tab.id, openBackgroundImageInNewTab, info))[0].result;
            console.log("url: ", url, url ? 1:0);
            if (!url) return;
            await chrome.tabs.create({
                url: url,
                index: tab.index + 1
            });
        }
    },
    ytdlp: {
        parentId: "downloadRoot",
        title: "使用 provider 自動判斷下載",
        contexts: ["selection", "link", "page"],
        script: async (info, tab) => {
            const target = info.selectionText || info.linkUrl || tab.url;
            await submitCurrentTarget(target, { tab, providerHint: info.selectionText ? null : inferProviderHint(target) });
        },
        documentUrlPatterns: [
            "https://www.youtube.com/*",
            "https://youtu.be/*",
            "https://www.facebook.com/reel/*",
            "https://www.facebook.com/watch/*",
            "https://x.com/*",
            "https://twitter.com/*"
        ]
    },
    // 手機板轉為桌面版區，以後可能要獨立出來
    taobaoMobile2Desktop: {
        title: "淘寶轉為桌面版",
        contexts: ["page"],
        script: async (info, tab) => {
            // https://m.intl.taobao.com/detail/detail.html?id=906139554065
            // to
            // https://item.taobao.com/item.htm?id=906139554065
            const url = tab.url.replace("m.intl.taobao.com/detail/detail.html", "item.taobao.com/item.htm");
            await chrome.tabs.update(tab.id, { url });
        },
        documentUrlPatterns: ["https://m.intl.taobao.com/*"]
    },
    bahaMobile2Desktop: {
        title: "巴哈姆特轉為桌面版",
        contexts: ["page"],
        script: async (info, tab) => {
            // https://m.gamer.com.tw/forum
            // to
            // https://forum.gamer.com.tw/
            const url = tab.url.replace("m.gamer.com.tw/forum", "forum.gamer.com.tw");
            await chrome.tabs.update(tab.id, { url });
        },
        documentUrlPatterns: ["https://m.gamer.com.tw/*"]
    }
};

// ########################################################
// #                                                      #
// #                     redirector                       #
// #                                                      #
// ########################################################

export const redirectOptions = [
    // old pixiv to new pixiv
    // {
    //     reg: "https://www.pixiv.net/member_illust.php\\\\?mode=medium&illust_id=(\\d+)",
    //     url: "https://www.pixiv.net/artworks/$1",
    // },
    // remove "fbclid" query from url
    {
        query: {
            remove: ["fbclid"],
        }
    },
    {
        host: ["twitter.com", "mobile.twitter.com", "x.com"],
        query: {
            remove: ["t", "s"],
        }
    }
]

// ########################################################
// #                                                      #
// #                      omnibox                         #
// #                                                      #
// ########################################################

export const omniboxCallback = {
    currencyTrans: {
        onInputChanged: async (text, suggest) => {
            // api site: https://app.exchangerate-api.com/dashboard/confirmed
            const exangeKey = key["exchangerate-api.com"];
            if (!exangeKey) {
                suggest([
                    { content: "請先設定 exchangerate-api.com API key", description: "請先設定 exchangerate-api.com API key" }
                ]);
                return;
            }

            storeData.currency = storeData.currency || {};
            // if inputed text format "<number> <currency> to <currency>"
            let [_, amount, from, to] = text.match(/(\d+\.?\d*)\s*([a-zA-Z]{3})\s*to\s*([a-zA-Z]{3})/i) || [];
            if (amount && from && to) {
                const transDict = {
                    RMB: "CNY",
                    NTD: "TWD",
                }

                from = transDict[from.toUpperCase()] || from.toUpperCase();
                to = transDict[to.toUpperCase()] || to.toUpperCase();

                // to is main currency
                // find if from or to not in storeData.currency {c: {C0: rate0, C1: rate1, ...}}
                const isRate = storeData.currency[to]?.[from];
                // console.log("rate: ", rate, storeData.currency, from, to);

                // if rate is found
                // call api https://v6.exchangerate-api.com/v6/<key>/latest/<currency>
                if(!isRate){
                    const rateData = await fetch(`https://v6.exchangerate-api.com/v6/${ key["exchangerate-api.com"] }/latest/${ to }`)
                        .then(res => res.json());

                    // console.log("rateData: ", rateData);
                    const conversion_rates = rateData.conversion_rates;
                    storeData.currency[to] = conversion_rates;
                    for (const [c, r] of Object.entries(conversion_rates)) {
                        storeData.currency[c] = storeData.currency[c] || {};
                        storeData.currency[c][to] = 1 / r;
                    }
                }

                // calculate amount
                const result = amount / (storeData.currency[to][from] || 1);

                // suggest result
                suggest([
                    { content: result.toFixed(2), description: `${ amount } ${ from } = ${ result.toFixed(2) } ${ to }` }
                ]);
            }
        }
    }
}