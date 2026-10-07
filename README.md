# ClauseGuard

ClauseGuard is a completed student/research prototype for analyzing, standardizing, and tracking privacy policy risks across digital services.

## Features
* **Privacy-policy extraction**: Extracts privacy clauses from raw policy text.
* **Canonicalization**: Normalizes disparate data terms into canonical entities.
* **Portfolio storage**: Securely stores the privacy footprint in a local SQLite database.
* **Risk scoring**: Quantifies clause and service risks via severity and specificity parameters.
* **Marginal risk**: Calculates the exact added risk a candidate service introduces to an existing portfolio.
* **Evaluation**: A strictly validated, mathematically sound evaluation foundation with anti-leakage systems.
* **Live dashboard**: A Flask-based interactive portfolio dashboard.
* **Chrome extension**: A lightweight browser extension for analyzing policies on the fly.

## Architecture
```
Privacy Policy webpage
       ↓
Chrome Extension (Client)
       ↓
Flask Backend /api/analyze-policy
       ↓
[C1] Extraction (Prefilter + LLM)
       ↓
[C2] Canonicalization
       ↓
[C4] Scoring Engine & [C5] Marginal Risk
       ↓
[C3] SQLite Portfolio Storage (Local DB)
```

## Requirements
* Python 3.9+
* Required dependencies are listed in `requirements.txt`.

## Setup

Run the following commands in your terminal (Windows):

```powershell
cd D:\clauseguard
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Compare two websites

Start the dashboard, then paste two website links (for example `spotify.com` and `apple.com`).
ClauseGuard finds each site's privacy policy and terms, scores them, and recommends the more private one,
with reasons, a data-type comparison, detected practices (selling data, deletion rights, etc.) and the riskiest statements.
If a site blocks automatic access, choose "Paste policy text instead". The API is `POST /api/compare-websites`.
Links to local/private network addresses are refused unless `CLAUSEGUARD_ALLOW_PRIVATE=1` is set (used by the tests).

The portfolio starts empty. Use **Save to portfolio** on a comparison to add services (and **Remove** on the My portfolio tab). The previous sample data (Spotify and a leftover "Policies" entry) is kept in `data/db/portfolio_sample.db`.

## Run Demo

Run the end-to-end Python demo (spins up a temporary DB to protect your real portfolio):
```powershell
python run_demo.py
```

## Run Dashboard

Start the live dashboard:
```powershell
python src/dashboard.py
```
Then open your web browser to: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Real API Integration (Gemini)

ClauseGuard natively integrates with Google's Gemini API for semantic entity extraction.

1. **MOCK/DEV Mode (Default):** If no API key is provided, ClauseGuard automatically uses a deterministic regex fallback mode for local testing. It clearly marks results with `mode: "MOCK/DEV"`.
2. **Real Gemini Mode:** To enable real semantic extraction:
   ```powershell
   set GEMINI_API_KEY=YOUR_REAL_KEY
   set GEMINI_MODEL=gemini-1.5-flash
   python src/dashboard.py
   ```
   A successful API request will mark the extracted service with `mode: "GEMINI"`. If the API fails or you hit rate limits, the request explicitly errors rather than silently falling back to mock data. API limits depend entirely on your Google account.

## Chrome Extension

To use the Chrome Extension:
1. Ensure the backend is running (`python src/dashboard.py`).
2. Open Chrome and navigate to `chrome://extensions/`.
3. Enable **Developer mode** in the top right.
4. Click **Load unpacked** and select the `D:\clauseguard\extension` directory.
5. Open a real privacy policy webpage (e.g., Spotify's privacy policy).
6. Click the ClauseGuard extension icon and click **Analyze Policy**.

*(Note: Chrome integration has been verified against proxy payloads, but not manually verified inside an actual physical browser instance.)*

## Testing

Run the full automated test suite:
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Prototype Limitations
Please note the following constraints on this prototype:
* **Production ML:** The system is an MVP concept. The ML Prefilter is trained on an 8-sentence mock dataset, not OPP-115.
* **Risk Probability:** Risk scores are deterministic calculations, not empirically verified probabilities of privacy breaches.
* **Marginal Overlap:** The overlap system discounts overlapping clauses by a hardcoded deterministic factor (`W_overlap=0.5`). 
