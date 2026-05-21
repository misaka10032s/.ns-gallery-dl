

export const useUtils = (install = false) => {
    // download mulpiple images
    const downloadMultipleImgs = async (tab, urlsObjects, delay=200) => {
        for(let index = 0; index < urlsObjects.length; index++){
            const urlsObject = urlsObjects[index];
            if(!urlsObject) continue;
            
            try{
                // because maximum 10 download at the same time, so set a delay to prevent overflow
                await new Promise(resolve => setTimeout(resolve, delay));
                
                await fetch(urlsObject.url).then(async r => {
                    const blobUrl = URL.createObjectURL(await r.blob());

                    const anchor = document.createElement("a");
                    anchor.href = blobUrl;
                    anchor.download = urlsObject.title;
                    document.body.appendChild(anchor);

                    anchor.click();

                    URL.revokeObjectURL(blobUrl);
                    document.body.removeChild(anchor);
                });
            }
            catch(e){
                console.error(e);
                Toast(1500).fire("error", "下載失敗 :(", e);
            }
        };
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    // transform image to blob object
    const image2Blob = async (image) => {
        if(!image) return;
        const imgUrl = typeof image === "string" ? image : image.src;

        const res = await fetch(imgUrl, {mode: "cors"});
        if(!res.ok) return;
        return await res.blob();
    }

    // transform image to canvas
    // image: image element or image url
    const image2Canvas = async (image) => {
        const blob = await image2Blob(image);
        if(!blob) return;

        // Convert the image blob to image using a canvas
        const imageBitmap = await createImageBitmap(blob);
        const canvas = document.createElement("canvas");
        canvas.width = imageBitmap.width;
        canvas.height = imageBitmap.height;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(imageBitmap, 0, 0);

        return canvas;
    }

    // transform image to base64
    // image: image element or image url
    const image2Base64 = async (image) => {
        const blob = await image2Blob(image);
        if(!blob) return;

        // Create a FileReader to convert the blob to a Base64 string
        const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result); // Base64 string will be here
            reader.onerror = () => reject("Error reading the Blob as Base64");
            reader.readAsDataURL(blob);
        });

        console.log("Base64 string:", base64);
        return base64;
    }

    // copy image to clipboard
    const copyImageToClipboard = async (image, type="png") => {
        const imageCanvas = await image2Canvas(image);
        if(!imageCanvas) return;
        try {
            const pngBlob = await new Promise(resolve => imageCanvas.toBlob(resolve, `image/${ type }`));

            // Create a ClipboardItem with the PNG blob
            const clipboardItem = new ClipboardItem({ [`image/${ type }`]: pngBlob });

            // Write the ClipboardItem to the clipboard
            await navigator.clipboard.write([clipboardItem]);

            console.log("Image copied to clipboard successfully!");
            // Toast(1500).fire("success", "圖片已複製到剪貼簿 :)");
        } catch (error) {
            console.error("Error copying image to clipboard:", error);
            // Toast(1500).fire("error", "複製失敗 :(", error);
        }
    }

    // copy text to clipboard
    const copyTextToClipboard = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
            console.log("Text copied to clipboard successfully!");
            // Toast(1500).fire("success", "文字已複製到剪貼簿 :)");
        } catch (error) {
            console.error("Error copying text to clipboard:", error);
            // Toast(1500).fire("error", "複製失敗 :(", error);
        }
    }

    const getDataFromClipboard = async (...type) => {
        const clipboardItems = await navigator.clipboard.read();
        for (const item of clipboardItems) {
            for (const t of type) {
                if (item.types.includes(t)) {
                    return await item.getType(t);
                }
            }
        }
    }

    // get image from clipboard
    const getImageFromClipboard = async (type="png") => {
        return await getDataFromClipboard(`image/${ type }`);
    }

    // get text from clipboard
    const getTextFromClipboard = async () => {
        return await getDataFromClipboard("text/plain");
    }

    // dispatch paste event
    // accept file or image as blob
    const pasteFile = async (target, blobData, name, fullType) => {
        if (!target) target=document.body;
        else if(typeof target === "string") target = document.querySelector(target);

        if(!target) return;

        const subType = fullType.split("/")[1];
        if (!blobData) blobData = await getImageFromClipboard(subType);
        else if (typeof blobData === "string") {
            // transform base64 string to blob
            const base64 = blobData.split(",")[1];
            const byteCharacters = atob(base64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            blobData = new Blob([byteArray], { type: fullType });
        }

        // if target is input[type="file"], add file to input not dispatch paste event
        if (target.tagName.toLowerCase() === "input" && target.type === "file") {
            const file = new File([blobData], `${ name }.${ subType }`, { type: fullType });
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            target.files = dataTransfer.files;
            target.dispatchEvent(new Event('change', { bubbles: true }));
            console.log("File added to input successfully!");
            return;
        }

        const file = new File([blobData], `${ name }.${ subType }`, { type: fullType });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        const pasteEvent = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: dataTransfer
        });
        target.dispatchEvent(pasteEvent);

        console.log("Image pasted successfully!");
        return;
    }

    // dispatch paste event
    // accept text as string
    const pasteText = async (target, text) => {
        if (!target) target=document.body;
        else if(typeof target === "string") target = document.querySelector(target);

        if(!target) return;
        if (!text) text = await getTextFromClipboard();

        const dataTransfer = new DataTransfer();
        dataTransfer.setData("text/plain", text);
        const pasteEvent = new ClipboardEvent('paste', {
            bubbles: true,
            cancelable: true,
            clipboardData: dataTransfer
        });
        target.dispatchEvent(pasteEvent);

        console.log("Text pasted successfully!");
        return;
    }

    const data = {
        downloadMultipleImgs,
        image2Blob,
        image2Canvas,
        image2Base64,
        copyImageToClipboard,
        copyTextToClipboard,
        getImageFromClipboard,
        getTextFromClipboard,
        pasteFile,
        pasteText,
    };

    if(install) {
        // install all utils to window
        for (const key in data) {
            window[key] = data[key];
        }
    }

    return data
}