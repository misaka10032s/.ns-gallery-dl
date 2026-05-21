import { contextMenus, redirectOptions, omniboxCallback } from "./static/module/menu.js";
import { executeScript, getDomain, executeStoreScript, redirectUrl, handleMessage } from "./static/module/core.js";
import { tabStore, tabVars } from "./static/module/store.js";
import { _initSwal } from "./static/js/sweetalert2@11.js";
import { useUtils } from "./static/module/utils.js";

// ########################################################
// ######################### menus ########################
// ########################################################
// created contextMenus
chrome.contextMenus.removeAll(function() {
    const menuIds = new Set();
    for (const [key, value] of Object.entries(contextMenus)) {
        // check if the id is created
        if (menuIds.has(key)) {
            continue;
        }
    
        var x = chrome.contextMenus.create({
            id: key,
            parentId: value.parentId,
            type: value.type ?? "normal",
            title: value.title,
            contexts: value.contexts,
            documentUrlPatterns: value.documentUrlPatterns,
        });
        menuIds.add(x);
    }
});

// ########################################################
// ####################### listener #######################
// ########################################################
// onClicked listener
chrome.contextMenus.onClicked.addListener(
    async (info, tab) => {
        console.log('info: ', info, 'tab: ', tab);
        if (info.menuItemId in contextMenus) {
            await contextMenus[info.menuItemId].script(info, tab);
        }
    }
);

// onUpdated listener
chrome.tabs.onUpdated.addListener(async function (tabId, changeInfo, tab) {
    // console.log("onUpdated tabId: ", tabId, changeInfo, tab);
    if (!tab.url.match("^http") /*&& !tab.url.match(`^chrome-extension://${ chrome.runtime.id }`)*/) {
        return;
    }
    // execute script when tab is loading
    if (changeInfo.status === 'loading') {
        // deprecated
        // executeScript(tabId, redirectUrl, redirectOptions);
    }
    // execute script when tab is completely loaded
    if (changeInfo.status === 'complete') {
        if (tabId in tabStore.ids) {
            console.log("executeScript: ", tabId, tabStore.ids[tabId]);
            executeStoreScript(tabStore.ids, tabId, tab);
        }

        const domain = getDomain(tab.url);
        if (domain in tabStore.domains) {
            console.log("executeScript: ", domain, tabStore.domains[domain]);
            executeStoreScript(tabStore.domains, domain, tab);
        }

        for(let i in tabStore.always){
            console.log("executeScript: ", tabStore.always[i]);
            executeStoreScript(tabStore.always, i, tab);
        }

        // init Swal for each tab
        tabVars[tabId] = {};
        executeScript(tabId, _initSwal);
        executeScript(tabId, handleMessage);
        executeScript(tabId, useUtils, true);
    }
});

chrome.webNavigation.onBeforeNavigate.addListener(
    async function(details) {
        // redirector
        // console.log("details", details);
        let origUrl = details.url;
        // console.log("old href", origUrl)
        const {newUrl, isChanged} = redirectUrl(redirectOptions, origUrl);
        // console.log("new href", newUrl, isChanged);
        if(isChanged) chrome.tabs.update(details.tabId, {url: newUrl});
    },
    {urls: ["<all_urls>"]}
);

chrome.commands.onCommand.addListener((command) => {
    console.log(`Command "${command}" triggered`, command == "Ctrl+B", command == "Ctrl+Shift+Z");
    switch (command) {
        case "Ctrl+B":
            break;
        case "A+B+C":
            break;
        default:
            break;
    }
});

chrome.omnibox.setDefaultSuggestion({ description: "歡迎使用 NStools" });
for(const [key, value] of Object.entries(omniboxCallback)){
    if(value.onInputChanged){
        chrome.omnibox.onInputChanged.addListener(value.onInputChanged);
    }
}
// example
// chrome.omnibox.onInputChanged.addListener((text, suggest) => {
//     suggest([
//         { content: "color:#228B22", description: "Green", deletable: true },
//     ]);
//     chrome.omnibox.setDefaultSuggestion({ description: "Error fetching conversion rate." });
// });

chrome.runtime.onInstalled.addListener(() => {
  chrome.scripting.registerContentScripts([
    {
      id: "overrideOnCopyAndPaste",
      matches: ["https://www.dailydaily-up.com/*"],
      js: ["static/js/antiPreventCopy.js"],
      runAt: "document_start"
    }
  ]);
});