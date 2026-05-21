import { API_BASE, fetchDashboardSummary, submitLinks } from "../../../core/api.js";
import { getSiteAction, inferProviderHint } from "../../../core/targets.js";

const serverChip = document.getElementById("server-chip");
const queueChip = document.getElementById("queue-chip");
const tabTitle = document.getElementById("tab-title");
const tabUrl = document.getElementById("tab-url");
const downloadCurrentButton = document.getElementById("download-current");
const openDashboardButton = document.getElementById("open-dashboard");
const openJobsButton = document.getElementById("open-jobs");
const openHistoryButton = document.getElementById("open-history");

async function getActiveTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
}

function openLocalPage(path) {
    chrome.tabs.create({ url: `${API_BASE}${path}` });
}

async function refreshStatus() {
    try {
        const dashboard = await fetchDashboardSummary();
        serverChip.textContent = "Server 已連線";
        serverChip.className = "chip ok";
        queueChip.textContent = `Queue ${dashboard.queue.total}`;
    } catch (error) {
        serverChip.textContent = "Server 未連線";
        serverChip.className = "chip bad";
        queueChip.textContent = "Queue --";
    }
}

async function refreshTabAction() {
    const tab = await getActiveTab();
    tabTitle.textContent = tab?.title || "目前分頁";
    tabUrl.textContent = tab?.url || "無法取得目前頁面 URL";

    const action = tab?.url ? getSiteAction(tab.url) : null;
    downloadCurrentButton.textContent = action ? action.label : "下載目前頁面";

    downloadCurrentButton.onclick = async () => {
        if (!tab?.url) return;
        await submitLinks([tab.url], {
            sender: { tab },
            providerHint: action?.providerHint ?? inferProviderHint(tab.url),
            source: "extension",
        });
    };
}

openDashboardButton.addEventListener("click", () => openLocalPage("/"));
openJobsButton.addEventListener("click", () => openLocalPage("/jobs"));
openHistoryButton.addEventListener("click", () => openLocalPage("/history"));

await refreshStatus();
await refreshTabAction();