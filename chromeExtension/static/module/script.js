import { tabStore } from "./store.js";
import { downloadImages } from "./core.js";
import { useUtils } from "./utils.js";
/*
    reloadImage: reload all images which loaded failure on the page
    anitWhite: remove the site to prevent user select
    navigation: goto the certained site
    searchSaucenao: search the image on saucenao
    searchAscii2d: search the image on ascii2d
*/

// @reloadImage
export const reloadImage = () => {
    console.log("reloading image");
    [...document.getElementsByTagName("img")].forEach(e=>{if(e.width==16)e.src=e.src;})
}

// @anitWhite
export const anitWhite = () => {
    console.log("anti-white");
    function R(a) {
        ona = "on" + a;
        if (window.addEventListener) window.addEventListener(a, function (e) {
            for (var n = e.originalTarget; n; n = n.parentNode) n[ona] = null; 
        }, true);
        window[ona] = null;
        document[ona] = null;
        if (document.body) document.body[ona] = null; 
    }
    R("contextmenu");
    R("click");
    R("mousedown");
    R("mouseup");
    R("selectstart");
    R("keydoun");
    R("keyup");
}

// @navigation
export const navigation = (input) => {
    // const input = new URLSearchParams(window.location.search).get("href");
    console.log(input)
    const [_, prefix, ..._number] = input.toLowerCase().match(/([a-z]?)([\s0-9]+)/) ?? [];
    const number = _number.join("").replace(/\s/g, ""); console.log(prefix, number);

    const links = {
        "n": ["http://nhentai.net/g/", ""],
        // "n": ["http://nhentai.website/g/", ""],
        "w": ["https://www.wnacg.com/photos-index-aid-", ".html"],
        "p": ["https://www.pixiv.net/artworks/", ""],
    }

    const goto = linkName => {
        if(linkName in links){
            window.open(links[linkName].join(number), target="_blank");
        }
    }

    if(prefix in links) goto(prefix);
    else if(number){
        const numberValue = parseInt(number);
        if(number.length == 6) goto("n");
        else if(number.length == 5) goto("w");
        else if(1E7 < numberValue && numberValue < 1.3E9) goto("p");
    }
}

// @searchSaucenao
export const searchSaucenao = {
    img2Base64: async (imgUrl) => {
        return await image2Base64(imgUrl);
    },
    addUrl: (imgUrl) => {
        document.getElementById("urlInput").value = imgUrl;
        document.getElementById("urlInput").dispatchEvent(new CustomEvent("blur"));
        document.getElementById("searchButton").click();
    },
    addBlob: (base64) => {
        pasteFile("#fileInput", base64, "image.png", "image/png").then(() => {
            setTimeout(() => {
                 document.getElementById("searchButton").click();
            }, 50);
        });
    }
}

// @searchAscii2d
export const searchAscii2d = {
    img2Base64: async (imgUrl) => {
        return await image2Base64(imgUrl);
    },
    addUrl: (imgUrl) => {
        document.getElementById("uri-form").value = imgUrl;
        document.getElementById("uri-form").parentElement.nextElementSibling.children[0].click();
    },
    addBlob: (base64) => {
        pasteFile("#file-form", base64, "image.png", "image/png").then(() => {
            setTimeout(() => {
                document.getElementById("file-form").parentElement.nextElementSibling.children[0].click();
            }, 50);
        });
    }
}

// @searchSoutubot
export const searchSoutubot = {
    img2Base64: async (imgUrl) => {
        return await image2Base64(imgUrl);
    },
    addBlob: (base64) => {
        // group relative overflow-hidden flex flex-col justify-center items-center rounded-lg border border-dashed border-gray-500 w-full h-60 sm:h-[300px] cursor-pointer sm:hover:bg-gray-900/50
        const divEl = document.querySelector("div.group.relative");
        const inputEl = divEl.nextElementSibling;
        pasteFile(inputEl, base64, "image.png", "image/png");
    }
}

// @searchTraceMoe
export const searchTraceMoe = {
    img2Base64: async (imgUrl) => {
        return await image2Base64(imgUrl);
    },
    addUrl: (imgUrl) => {
        const input = document.querySelector("input[type='url']");
        input.value = imgUrl;
        // dispatch input event
        input.dispatchEvent(new Event("input", { bubbles: true }));
    },
    addBlob: (base64) => {
        pasteFile("input[type='url']", base64, "image.png", "image/png");
    }
}

// @getBahaImg
export const getBahaImg = (tab, actionType=1) => {
    var element = document.cElement;
    const imgUrls = [];
    const imgEls = [];

    const title = document.querySelector(".c-post__header__title").innerText;
    var article = [];
    // determine get all floors or only the clicked floor
    while(element){// c-article FM-P2
        if(element.classList.contains("c-article") && element.classList.contains("FM-P2")){
            article = [element];
            break;
        }
        element = element.parentElement;
    }
    if(!article.length) article = [...document.getElementsByClassName("c-article FM-P2")];

    // get baha every floor img
    article.forEach(
        e => [...e.getElementsByTagName("img")].forEach(
            imgEl => {
                imgUrls.push(imgEl.getAttribute("data-src"));
                imgEls.push(imgEl);
            }
        )
    );
    console.log(imgUrls);

    const { copyTextToClipboard } = useUtils();
    if(actionType & 1) copyTextToClipboard(JSON.stringify(imgUrls));

    return imgUrls.map((e, i) => {
        const imgExtension = e.split(".").pop();
        return {
            url: e,
            title: `${title}-${i}.${imgExtension}`,
        }
    }).filter(e => e.url != null);
}
// record the clicked element at bahamut
tabStore.domains["forum.gamer.com.tw"] = {
    script: (tab) => {
        if(!document.cElement) document.cElement = null;
        document.addEventListener("contextmenu", e => {
            document.cElement = document.elementFromPoint(e.x, e.y);
        })
    }
}

tabStore.domains["www.instagram.com"] = {
    script: (tab) => {
        const s = setInterval(() => {
            // 移除阻擋右鍵存圖
            [...document.querySelectorAll("._aagw")].forEach(e => e.remove())
        }, 200);
    }
}

// export chatGPT as image
export const exportChatGPTConversation = () => {
    // div: @thread-xl/thread:pt-header-height mt-1.5 flex flex-col text-sm
    const allChat = [...document.querySelectorAll("div")].filter(x => x.classList.contains("@thread-xl/thread:pt-header-height"))[0];
    const title = document.querySelector("title").innerText;
    html2canvas(allChat, {
        backgroundColor: "#212121",
    }).then(function(canvas) {
        // trans canvas to image
        canvas.toBlob(function(blob) {
            const blobUrl = URL.createObjectURL(blob);
            const img = new Image();
            img.src = blobUrl;

            const a = document.createElement("a");
            a.href = blobUrl;
            a.download = title;
            a.appendChild(img);

            // open img as new tab
            const w = window.open("");
            // write img to new tab
            w.document.write(a.outerHTML);
            // set title
            w.document.title = title;
        }, "image/png");
    });
}

// qrcode / barcode decoder
// Three distinguishable outcomes (the old version could only ever show nothing on a decoder-internal
// failure, which looked identical to "no code in this image" — that ambiguity was the actual complaint):
//   1. decoded successfully -> success Toast with the text + symbology
//   2. decoder ran the full ladder and found nothing -> "not found" Toast
//   3. the decode attempt itself threw (wasm/runtime failure) -> "error" Toast
// decodeQrOrBarcode (static/js/QrBarcodeReader.js, injected by menu.js before this runs) implements the
// preprocessing ladder and encodes outcomes 2 vs 3 as return-null vs throw.
export const deQrcode = async () => {
    const image = document.clickedImage;
    const { copyTextToClipboard } = useUtils();

    let blob;
    try {
        const r = await fetch(image.src);
        blob = await r.blob();
    } catch (e) {
        Toast(1500).fire("error", "圖片讀取失敗 :(", String(e));
        return;
    }

    const image2 = new Image();
    image2.onerror = () => {
        Toast(1500).fire("error", "圖片載入失敗 :(", "");
    };
    image2.onload = async () => {
        try {
            const canvas = document.createElement("canvas");
            canvas.width = image2.naturalWidth;
            canvas.height = image2.naturalHeight;
            canvas.getContext("2d").drawImage(image2, 0, 0);
            const imageData = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height);

            const result = await decodeQrOrBarcode(imageData);
            if (result) {
                copyTextToClipboard(result.text);
                Toast(3000).fire("解析成功", `[${result.format}] ${result.text}`);
            } else {
                Toast(2000).fire("找不到條碼", "此圖片中未偵測到 QR code 或條碼");
            }
        } catch (e) {
            Toast(1500).fire("error", "解析發生錯誤 :(", String(e?.message ?? e));
        }
    };
    image2.src = URL.createObjectURL(blob);
}

export const getPixivAllImg = async (info) => {
    // page url: https://www.pixiv.net/artworks/123793853
    // image url: https://i.pximg.net/img-original/img/2024/10/29/21/21/19/123793853_p0.jpg

    // title class: sc-a2ee6855-3 kQqnJS
    // const title = document.querySelector(".sc-a2ee6855-3.kQqnJS").innerText;

    // get image url
    const imageNumber = info.frameUrl.split("/").pop();
    // get image number
    const imgUrls = [...document.querySelectorAll("a")].map(e => e.href).filter(e => e.includes(imageNumber)).filter(e => e.includes("i.pximg.net"));
    return imgUrls.map((e, i) => {
        const imgExtension = e.split(".").pop();
        return {
            url: e,
            title: `${imageNumber}_p${i}.${imgExtension}`,
        }
    });
}

export const openBackgroundImageInNewTab = (info) => {
    const selectedObjects = document.clickedElements;
    
    const imageDiv = selectedObjects.filter(e => window.getComputedStyle(e).backgroundImage != "none")[0];

    if(!imageDiv) return;
    const bgImage = window.getComputedStyle(imageDiv).backgroundImage;

    const url = bgImage.replace(/url\(["']?/, "").replace(/["']?\)/, "");
    return url;
}

tabStore.always.push(...[{
    script: (tab) => {
        document.addEventListener("contextmenu", e => {
            const eles = document.elementsFromPoint(e.x, e.y);
            document.clickedImage = eles.filter(e => e instanceof Image && e.src)[0];
            document.clickedElements = eles;
        })
    }
}, {
    script: anitWhite
}])