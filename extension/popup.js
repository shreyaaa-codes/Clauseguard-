document.addEventListener('DOMContentLoaded', () => {
    let currentAnalysisResult = null;
    const siteNameSpan = document.getElementById('site-name');
    const analyzeBtn = document.getElementById('analyze-btn');
    const statusDiv = document.getElementById('status');
    const resultsDiv = document.getElementById('results');
    const toggleClausesBtn = document.getElementById('toggle-clauses-btn');
    const clausesDetailsDiv = document.getElementById('clauses-details');

    // Get current tab info
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        const activeTab = tabs[0];
        if (activeTab && activeTab.url) {
            try {
                const url = new URL(activeTab.url);
                siteNameSpan.textContent = url.hostname;
            } catch (e) {
                siteNameSpan.textContent = "Unknown";
            }
        }
    });

    function showStatus(msg, type = "info") {
        statusDiv.textContent = msg;
        statusDiv.className = `status ${type}`;
        statusDiv.classList.remove('hidden');
    }

    function hideStatus() {
        statusDiv.classList.add('hidden');
    }

    analyzeBtn.addEventListener('click', () => {
        analyzeBtn.disabled = true;
        resultsDiv.classList.add('hidden');
        showStatus("Extracting page text...", "info");

        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            const activeTab = tabs[0];

            if (activeTab.url.startsWith('chrome://')) {
                showStatus("Cannot analyze chrome:// pages.", "error");
                analyzeBtn.disabled = false;
                return;
            }

            // Inject content script and ask for text
            chrome.scripting.executeScript({
                target: { tabId: activeTab.id },
                files: ['content.js']
            }, () => {
                if (chrome.runtime.lastError) {
                    showStatus("Failed to inject script: " + chrome.runtime.lastError.message, "error");
                    analyzeBtn.disabled = false;
                    return;
                }

                chrome.tabs.sendMessage(activeTab.id, { action: "extract_text" }, (response) => {
                    if (chrome.runtime.lastError || !response) {
                        showStatus("ClauseGuard couldn't analyze this page. Please refresh and try again.", "error");
                        analyzeBtn.disabled = false;
                        return;
                    }

                    if (!response.text || response.text.trim().length === 0) {
                        showStatus("No readable text found on this page.", "error");
                        analyzeBtn.disabled = false;
                        return;
                    }

                    if (!response.isLikelyPrivacyPolicy) {
                        if (!confirm("This page does not appear to be a privacy policy. Do you want to scan it anyway?")) {
                            hideStatus();
                            analyzeBtn.disabled = false;
                            return;
                        }
                    }

                    if (response.truncated) {
                        showStatus("Text is very large. Sending first 50k characters to backend...", "warning");
                    } else {
                        showStatus("Sending to ClauseGuard backend...", "info");
                    }

                    sendToBackend(response);
                });
            });
        });
    });

    async function sendToBackend(data) {
        try {
            const res = await fetch("http://127.0.0.1:5000/api/analyze-policy", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    text: data.text,
                    url: data.url,
                    title: data.title
                })
            });

            if (!res.ok) {
                let errText = "Backend error.";
                try {
                    const errObj = await res.json();
                    errText = errObj.error || errText;
                } catch(e) {}
                throw new Error(errText);
            }

            const result = await res.json();
            displayResults(result);

        } catch (error) {
            if (error.message.includes("Failed to fetch")) {
                showStatus("Start ClauseGuard backend first: python src/dashboard.py", "error");
            } else {
                showStatus(`Analysis failed: ${error.message}`, "error");
            }
            analyzeBtn.disabled = false;
        }
    }

    function displayResults(data) {
        hideStatus();
        analyzeBtn.disabled = false;
        resultsDiv.classList.remove('hidden');

        document.getElementById('risk-score').textContent = data.risk.toFixed(1);
        document.getElementById('api-mode').textContent = data.mode;

        // Mode styling
        const modeEl = document.getElementById('mode-indicator');
        if (data.mode === "MOCK/DEV") {
            modeEl.style.backgroundColor = "#fef08a"; // yellow
            modeEl.style.color = "#854d0e";
        } else {
            modeEl.style.backgroundColor = "#bbf7d0"; // green
            modeEl.style.color = "#166534";
        }

        const entitiesList = document.getElementById('entities-list');
        entitiesList.innerHTML = '';
        if (data.canonical_entities.length === 0) {
            entitiesList.innerHTML = '<li>None detected</li>';
        } else {
            data.canonical_entities.forEach(ent => {
                const li = document.createElement('li');
                li.textContent = ent;
                entitiesList.appendChild(li);
            });
        }

        document.getElementById('clause-count').textContent = data.clauses.length;

        clausesDetailsDiv.innerHTML = '';
        data.clauses.forEach(c => {
            const card = document.createElement('div');
            card.className = 'clause-card';

            // Limit text length in UI
            let text = c.text;
            if (text.length > 150) {
                text = text.substring(0, 150) + '...';
            }

            const risk = ((c.severity_score || 0) + (c.specificity_score || 0)).toFixed(1);

            card.innerHTML = `
                <div class="clause-text">"${text}"</div>
                <div class="clause-meta">
                    <span>Cat: ${c.risk_category || 'N/A'}</span>
                    <span>Risk: ${risk}</span>
                </div>
            `;
            clausesDetailsDiv.appendChild(card);
        });

        currentAnalysisResult = data;
        const saveBtn = document.getElementById('save-btn');
        const saveStatus = document.getElementById('save-status');
        saveBtn.disabled = false;
        saveBtn.textContent = "Add to Portfolio";
        saveStatus.classList.add('hidden');
    }

    toggleClausesBtn.addEventListener('click', () => {
        if (clausesDetailsDiv.classList.contains('hidden')) {
            clausesDetailsDiv.classList.remove('hidden');
            toggleClausesBtn.textContent = "Hide Details";
        } else {
            clausesDetailsDiv.classList.add('hidden');
            toggleClausesBtn.textContent = "View Details";
        }
    });

    const saveBtn = document.getElementById('save-btn');
    const saveStatus = document.getElementById('save-status');

    saveBtn.addEventListener('click', async () => {
        if (!currentAnalysisResult) return;

        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";
        saveStatus.classList.add('hidden');

        try {
            const res = await fetch("http://127.0.0.1:5000/api/save-service", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(currentAnalysisResult)
            });

            if (!res.ok) {
                let errText = "Failed to save.";
                try {
                    const errObj = await res.json();
                    errText = errObj.error || errText;
                } catch(e) {}
                throw new Error(errText);
            }

            saveBtn.textContent = "Added to Portfolio";
            saveStatus.textContent = "Successfully saved!";
            saveStatus.className = "status success";
            saveStatus.classList.remove('hidden');

        } catch (error) {
            saveBtn.disabled = false;
            saveBtn.textContent = "Retry Add";
            saveStatus.textContent = `Error: ${error.message}`;
            saveStatus.className = "status error";
            saveStatus.classList.remove('hidden');
        }
    });
});
