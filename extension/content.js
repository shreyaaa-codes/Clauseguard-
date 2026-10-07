// Extract text from the page safely
function extractPageText() {
    // Basic heuristic cleanup: remove hidden elements, scripts, styles
    const clone = document.body.cloneNode(true);
    
    const elementsToRemove = clone.querySelectorAll('script, style, nav, footer, header, noscript, iframe');
    elementsToRemove.forEach(el => el.remove());

    let text = clone.innerText || "";
    
    // Normalize excessive whitespace
    text = text.replace(/\s+/g, ' ').trim();
    
    // Sensible text limit (e.g. 50,000 characters to prevent overloading the backend)
    const MAX_LENGTH = 50000;
    const truncated = text.length > MAX_LENGTH;
    if (truncated) {
        text = text.substring(0, MAX_LENGTH);
    }
    
    // Basic heuristic to guess if this is a privacy policy
    const titleLower = document.title.toLowerCase();
    const urlLower = window.location.href.toLowerCase();
    const privacyKeywords = ['privacy policy', 'privacy notice', 'privacy statement', 'data protection', 'data policy', 'privacy'];
    
    let isLikelyPrivacyPolicy = false;
    if (privacyKeywords.some(kw => titleLower.includes(kw) || urlLower.includes(kw.replace(' ', '-')) || urlLower.includes(kw.replace(' ', '')))) {
        isLikelyPrivacyPolicy = true;
    }
    
    if (!isLikelyPrivacyPolicy) {
        const headings = Array.from(document.querySelectorAll('h1, h2, h3')).map(h => h.innerText.toLowerCase());
        if (headings.some(h => privacyKeywords.some(kw => h.includes(kw)))) {
            isLikelyPrivacyPolicy = true;
        }
    }
    
    const textPrefix = text.substring(0, 2000).toLowerCase();
    if (!isLikelyPrivacyPolicy && privacyKeywords.some(kw => textPrefix.includes(kw))) {
         isLikelyPrivacyPolicy = true;
    }

    let title = document.title;
    if (!title || title.trim() === "") {
        try {
            title = new URL(window.location.href).hostname;
        } catch(e) {
            title = "Unknown Service";
        }
    }

    return {
        text: text,
        url: window.location.href,
        title: title,
        truncated: truncated,
        isLikelyPrivacyPolicy: isLikelyPrivacyPolicy
    };
}

// Send response back to popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "extract_text") {
        const data = extractPageText();
        sendResponse(data);
    }
});
