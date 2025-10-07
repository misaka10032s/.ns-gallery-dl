const translations = {
    en: {
        pageTitle: "Download History",
        filterFrom: "From:",
        filterTo: "To:",
        btnLast1Day: "Last 1 Day",
        btnLast7Days: "Last 7 Days",
        btnLast30Days: "Last 30 Days",
        btnFilterByDomain: "Filter by Domain",
        btnClearFilters: "Clear Filters",
        selectedUrls: "Selected URLs",
        jsonMode: "JSON mode",
        modalTitle: "Filter by Domain",
        modalApplyBtn: "Apply Filters",
        noRecordsFound: "No history records match the current filters.",
        noHistoryFound: "No history found.",
        itemsSuffix: "items",
        filterStatus: "Status:",
        filterAll: "All",
        filterFailed: "Failed",
        filterSuccess: "Success",
        submitSelected: "Submit Selected",
        submitSuccessMsg: "Selected URLs have been sent to the download queue.",
        submitErrorMsg: "Failed to send URLs. Is the server running?",
        deselectAll: "Deselect All"
    },
    zh: {
        pageTitle: "下載歷史記錄",
        filterFrom: "從:",
        filterTo: "到:",
        btnLast1Day: "最近 1 天",
        btnLast7Days: "最近 7 天",
        btnLast30Days: "最近 30 天",
        btnFilterByDomain: "依網域篩選",
        btnClearFilters: "清除篩選",
        selectedUrls: "選取的 URL",
        jsonMode: "JSON 模式",
        modalTitle: "依網域篩選",
        modalApplyBtn: "套用篩選",
        noRecordsFound: "沒有符合條件的歷史記錄。",
        noHistoryFound: "找不到歷史記錄。",
        itemsSuffix: "個項目",
        filterStatus: "狀態：",
        filterAll: "全部",
        filterFailed: "僅失敗",
        filterSuccess: "僅成功",
        submitSelected: "送出所選",
        submitSuccessMsg: "已將選取的 URL 傳送到下載佇列。",
        submitErrorMsg: "傳送 URL 失敗。伺服器正在執行嗎？",
        deselectAll: "全部取消"
    },
    ja: {
        pageTitle: "ダウンロード履歴",
        filterFrom: "開始日:",
        filterTo: "終了日:",
        btnLast1Day: "過去 1 日間",
        btnLast7Days: "過去 7 日間",
        btnLast30Days: "過去 30 日間",
        btnFilterByDomain: "ドメインで絞り込み",
        btnClearFilters: "フィルターをクリア",
        selectedUrls: "選択したURL",
        jsonMode: "JSONモード",
        modalTitle: "ドメインで絞り込み",
        modalApplyBtn: "適用",
        noRecordsFound: "現在のフィルターに一致する履歴レコードはありません。",
        noHistoryFound: "履歴が見つかりません。",
        itemsSuffix: "件",
        filterStatus: "ステータス：",
        filterAll: "すべて",
        filterFailed: "失敗のみ",
        filterSuccess: "成功のみ",
        submitSelected: "選択を送信",
        submitSuccessMsg: "選択したURLをダウンロードキューに送信しました。",
        submitErrorMsg: "URLの送信に失敗しました。サーバーは実行されていますか？",
        deselectAll: "すべて選択解除"
    }
};

let currentLanguage = 'zh';

function setLanguage(lang) {
    if (!translations[lang]) {
        console.warn(`Language "${lang}" not found. Defaulting to 'zh'.`);
        lang = 'zh';
    }
    currentLanguage = lang;
    localStorage.setItem('language', lang);
    
    document.querySelectorAll('[data-lang-key]').forEach(element => {
        const key = element.getAttribute('data-lang-key');
        if (translations[lang][key]) {
            element.textContent = translations[lang][key];
        }
    });
    document.documentElement.lang = lang;
}

function getTranslation(key) {
    return translations[currentLanguage][key] || `[${key}]`;
}
