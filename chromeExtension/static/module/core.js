import { tabVars } from "./store.js";

export const executeScript = async (target, file, ...args) => {
    var tabId;
    console.trace("file", typeof file, file)
    // if target is "current", get current tab
    if (target == "current") {
        const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true
        });
        // if url is not start with "http", cancel
        if (!tab.url.match("^http")) return;
        // console.log("executeScript: ", tabId, tab);
        tabId = tab.id;
    }
    else tabId = target;

    if(!await checkTabById(tabId)) return;

    // if file is string, execute file
    if (typeof file == "string") {
        return await chrome.scripting.executeScript({
            target: {
                tabId: tabId
            },
            files: [`static/js/${file}`],
            // files: [`chrome-extension://${ chrome.runtime.id }/js/${ file }`],
        });
    }
    // if file is function, execute function
    else if (typeof file == "function") {
        return await chrome.scripting.executeScript({
            target: {
                tabId: tabId
            },
            func: file,
            args: args,
        });
    }
    // if file is an Array, check each item if all of them are string
    else if (Array.isArray(file)) {
        return await chrome.scripting.executeScript({
            target: {
                tabId: tabId
            },
            files: file.filter(item => typeof item == "string"),
        });
    }
}

export const getDomain = (url) => {
    const domain = url.match(/^https?:\/\/([^\/]+)/);
    return domain ? domain[1] : "";
}

// execute script in obj[key].script and delete obj[key] if obj[key].delete is true
export const executeStoreScript = async (obj, key, tab) => {
    if(!await checkTabById(tab?.id)) return;
    
    try {
        if (typeof obj[key].script == "function" || typeof obj[key].script == "string") {
            await executeScript(tab.id, obj[key].script, tab, ...(obj[key].args ?? []));
        }
    
        if (obj[key].delete) delete obj[key];
    } catch (e) {
        console.error("executeStoreScript error: ", e);
    }
}

export const redirectUrl = (options, origUrl) => {
    if (!origUrl && typeof window != "undefined") {
        origUrl = window.location.href;
    }
    var newUrl = origUrl;
    var isChanged = false;
    const host = new URL(origUrl).host;

    for (let i in options) {
        const rule = options[i];
        // if rule.host exists and is not match, continue
        if (rule.host){
            // if rule.host is String, check if it is match
            if (typeof rule.host == "string") {
                if (rule.host != host) continue;
            }
            // if rule.host is Array, check if it is match
            else if (Array.isArray(rule.host)) {
                if (!rule.host.includes(host)) continue;
            }
        }

        // use regexp, if rule.reg and rule.url are both exist
        if (rule.reg && rule.url) {
            const tmpReg = new RegExp(rule.reg);
            if (!newUrl.match(tmpReg)) continue;
            newUrl = newUrl.replace(tmpReg, rule.url);
            isChanged = true;
        }

        // use query, if rule.query is exist
        else if (rule.query) {
            const u = new URL(newUrl);
            // if rule.query.remove is String, delete it
            if (typeof rule.query.remove == "string") {
                // if not exist, continue
                if (!u.searchParams.has(rule.query)) continue;
                u.searchParams.delete(rule.query);
                isChanged = true;
            }
            // if rule.query.remove is Array, delete all of them
            else if (Array.isArray(rule.query.remove)) {
                for (let j in rule.query.remove) {
                    // if not exist, continue
                    if (!u.searchParams.has(rule.query.remove[j])) continue;
                    u.searchParams.delete(rule.query.remove[j]);
                    isChanged = true;
                }
            }

            // if rule.query.add is String, add it
            if (typeof rule.query.add == "string") {
                // if exist, continue
                if (u.searchParams.has(rule.query)) continue;
                u.searchParams.append(rule.query);
                isChanged = true;
            }
            // if rule.query.add is Array, add all of them
            else if (Array.isArray(rule.query.add)) {
                for (let j in rule.query.add) {
                    // if exist, continue
                    if (u.searchParams.has(rule.query.add[j])) continue;
                    u.searchParams.append(rule.query.add[j]);
                    isChanged = true;
                }
            }
            newUrl = u.href;
        }
    }
    if (typeof window != "undefined" && isChanged) window.history.replaceState({}, document.title, newUrl);
    return { newUrl, isChanged };
}

export const handleMessage = () => {
    // console.log("added listener");
    chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
        console.log(sender.tab ?
            "取得到tab，這是來自內容腳本的訊息：" + sender.tab.url
            : "沒有tab，這是來自擴充功能內部的訊息");
        if (request.greeting == "你好")
            sendResponse({ farewell: "再見" });
    });
};

// inject script to tab that can be used in window.$script or $script
export const injectScript = async (tabID, file) => {
    if(!tabVars[tabID]) tabVars[tabID] = {};
    if(!tabVars[tabID][file]){
        console.log("injectScript", tabID, file)
        await executeScript(tabID, file);
        tabVars[tabID][file] = true;
    }
}

// deprecated
// download images
export const downloadImages = async (images) => {
    console.log('chrome.downloads', chrome.downloads, images)
    images.forEach(image => {
        chrome.downloads.download({
            url: image,
            filename: image.split("/").pop()
        });
    });
}

// check if tab is exist
export const checkTabById = async (tabId) => {
    try{
        const tab = await chrome.tabs.get(tabId);
        if (!tab) {
            console.warn("tab not exist", tabId);
            return false;
        }
        return true;
    } catch(e){
        return false;
    }
}