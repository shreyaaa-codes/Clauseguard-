"""
ClauseGuard website analyzer.

Takes a website link (or pasted policy text), finds its privacy policy / terms,
runs the existing extraction -> canonicalization -> scoring pipeline, and builds
a detailed report. Two reports can then be compared to produce a recommendation.

Nothing in here writes to the portfolio database.
"""
import os
import re
import sys
import ipaddress
import socket
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extraction.prefilter import PrivacyPrefilter
from extraction.llm_extractor import LLMExtractor
from extraction.validator import validate_extraction_output
from canonicalize import EntityCanonicalizer
from scoring import ScoringEngine

MAX_PAGE_BYTES = 3_000_000
MAX_TEXT_CHARS = 250_000
MAX_CLAUSES = 200
FETCH_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; ClauseGuard/1.0; +privacy-policy-analysis)"

POLICY_LINK_WORDS = [
    ("privacy policy", 10), ("privacy notice", 10), ("privacy statement", 10),
    ("privacy", 8), ("data policy", 8), ("terms of service", 6),
    ("terms of use", 6), ("terms and conditions", 6), ("terms", 3), ("legal", 2),
]
COMMON_POLICY_PATHS = [
    "/privacy", "/privacy-policy", "/privacy-policy/", "/legal/privacy-policy",
    "/legal/privacy", "/policies/privacy", "/terms", "/terms-of-service",
]
PRIVACY_WORDS = re.compile(
    r"\b(collect\w*|share\w*|shar(?:e|ing)|disclos\w*|personal (?:data|information)|"
    r"cookies?|retain\w*|retention|third[- ]part\w+|advertis\w*|track\w*|location|"
    r"device|ip address|email|phone|biometric|payment|analytics|data)\b", re.I)

# --------------------------------------------------------------------------
# How sensitive is each kind of data? (1 = low, 5 = very sensitive)
# --------------------------------------------------------------------------
ENTITY_WEIGHT = {
    "Biometric Data": 5, "Precise Location": 5, "Payment Information": 5,
    "Communications": 4, "Location": 3, "Phone Number": 3, "Contact Information": 3,
    "Identifiers": 3, "Advertising Data": 3, "Email": 2, "Name": 2,
    "Account Information": 2, "Device Information": 2, "IP Address": 2,
    "Cookies": 2, "Usage Data": 2, "Analytics Data": 2, "Browser Information": 1,
    "General Data": 1,
}
ENTITY_GROUP = {
    "Name": "Identity", "Email": "Identity", "Phone Number": "Identity",
    "Contact Information": "Identity", "Account Information": "Identity",
    "Location": "Location", "Precise Location": "Location",
    "IP Address": "Device & browsing", "Device Information": "Device & browsing",
    "Browser Information": "Device & browsing", "Cookies": "Device & browsing",
    "Usage Data": "Device & browsing", "Identifiers": "Device & browsing",
    "Analytics Data": "Device & browsing",
    "Payment Information": "Financial", "Biometric Data": "Biometric",
    "Advertising Data": "Advertising", "Communications": "Communications",
}
GROUPS = ["Identity", "Location", "Device & browsing", "Financial", "Biometric",
          "Advertising", "Communications"]

# --------------------------------------------------------------------------
# Practices found by reading the full policy text.
# kind "risk" = bad for the user if present, "protect" = good for the user.
# --------------------------------------------------------------------------
PRACTICES = [
    ("sells_data", "risk", "Sells or monetises personal data",
     r"\b(?:we|may|can)\s+(?:(?!not\b|never\b)\w+\s+){0,6}sell\b[^.]{0,60}\b(?:personal|data|information)\b|\bsale of (?:your )?(?:personal )?(?:data|information)\b"),
    ("ad_sharing", "risk", "Shares data with advertisers or ad partners",
     r"\b(advertis\w+|marketing)\s+(partners?|networks?|companies|providers)\b|\bshare\b[^.]{0,80}\badvertis"),
    ("third_party", "risk", "Shares data with third parties",
     r"\b(share|disclose|provide|transfer)\b[^.]{0,80}\b(third[- ]part(y|ies)|partners|affiliates|service providers)\b"),
    ("cross_border", "risk", "Transfers data to other countries",
     r"\b(transfer\w*|process\w*|stor\w+)\b[^.]{0,80}\b(outside|other countries|internationally|united states|abroad|cross[- ]border)\b"),
    ("long_retention", "risk", "Keeps data for long or unspecified periods",
     r"\b(as long as (necessary|needed|your account)|indefinitely|retain\w*[^.]{0,60}(years|as long as))\b"),
    ("profiling", "risk", "Profiles users or makes automated decisions",
     r"\b(profil(e|ing)|automated decision|personali[sz]ed (ads|advertising)|inferences?)\b"),
    ("no_sale", "protect", "States that it does not sell personal data",
     r"\b(do(es)? not|don't|never|will not)\s+sell\b[^.]{0,50}\b(personal|data|information)\b"),
    ("delete_right", "protect", "Lets users delete or erase their data",
     r"\b(delete|erase|erasure|removal of)\b[^.]{0,60}\b(your|personal|account|data|information)\b"),
    ("access_right", "protect", "Lets users access or download their data",
     r"\b(access|download|export|portab\w+|copy of)\b[^.]{0,60}\b(your|personal)\b[^.]{0,30}\b(data|information)\b"),
    ("opt_out", "protect", "Offers an opt-out or privacy controls",
     r"\b(opt[- ]out|opt out|unsubscribe|privacy (settings|controls|choices)|withdraw (your )?consent|manage your (preferences|settings))\b"),
    ("security", "protect", "Describes security measures such as encryption",
     r"\b(encrypt\w*|secure (servers|storage)|security measures|safeguards?|ssl|tls)\b"),
    ("law_compliance", "protect", "Mentions privacy-law compliance (GDPR, CCPA, DPDP)",
     r"\b(gdpr|ccpa|cpra|dpdp|digital personal data protection|general data protection regulation)\b"),
]
PRACTICE_ADJUST = 4        # rating points per practice
PRACTICE_ADJUST_CAP = 12   # max total movement from practices


class AnalysisError(Exception):
    """Raised with a message that is safe to show to the user."""


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def _allow_private():
    return os.environ.get("CLAUSEGUARD_ALLOW_PRIVATE") == "1"


def normalize_url(raw):
    raw = (raw or "").strip()
    if not raw:
        raise AnalysisError("Enter a website link.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AnalysisError(f"'{raw}' is not a valid web link.")
    return raw


def _check_host_is_public(host):
    if _allow_private():
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise AnalysisError(f"Could not find '{host}'. Check the spelling of the link.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise AnalysisError("Links to local or private network addresses are not allowed.")


class _NoPrivateRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host_is_public(urllib.parse.urlparse(newurl).hostname or "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_get(url):
    """Returns (final_url, html_text). Raises AnalysisError."""
    _check_host_is_public(urllib.parse.urlparse(url).hostname)
    opener = urllib.request.build_opener(_NoPrivateRedirect)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype and ctype:
                raise AnalysisError(f"{url} is not a web page (got {ctype.split(';')[0]}).")
            raw = resp.read(MAX_PAGE_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.geturl(), raw.decode(charset, errors="replace")
    except AnalysisError:
        raise
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise AnalysisError(f"{urllib.parse.urlparse(url).hostname} blocked automatic access (HTTP {e.code}). "
                                "Open the policy in your browser and paste its text instead.")
        raise AnalysisError(f"{url} returned HTTP {e.code}.")
    except urllib.error.URLError as e:
        raise AnalysisError(f"Could not reach {url}: {e.reason}")
    except Exception as e:
        raise AnalysisError(f"Could not read {url}: {e}")


class _TextAndLinks(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form", "iframe", "template"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section",
             "article", "ul", "ol", "table", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts = []
        self.links = []          # (href, text)
        self._href = None
        self._link_text = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []
        if tag in self.SKIP and tag != "head":
            self.skip_depth += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._link_text).split())))
            self._href = None
        if tag in self.SKIP and tag != "head" and self.skip_depth:
            self.skip_depth -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._href is not None:
            self._link_text.append(data)
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html):
    p = _TextAndLinks()
    try:
        p.feed(html)
    except Exception:
        pass
    # Links inside skipped regions (nav/footer) are still collected, which is what we want:
    # privacy links usually live in the footer.
    lines = [" ".join(l.split()) for l in "".join(p.parts).split("\n")]
    text = "\n".join(l for l in lines if l)
    return text, p.links, " ".join(p.title.split())


def _privacy_density(text):
    words = max(len(text.split()), 1)
    return len(PRIVACY_WORDS.findall(text)) / words


def _looks_like_policy(text, url=""):
    if len(text) < 1500:
        return False
    if re.search(r"privacy|terms|legal|policy|policies", url, re.I):
        return _privacy_density(text) > 0.01
    return _privacy_density(text) > 0.03


def _rank_policy_links(base_url, links):
    seen, ranked = set(), []
    host = urllib.parse.urlparse(base_url).hostname or ""
    root = ".".join(host.split(".")[-2:])
    for href, label in links:
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        full = urllib.parse.urljoin(base_url, href).split("#")[0]
        p = urllib.parse.urlparse(full)
        if p.scheme not in ("http", "https") or full in seen:
            continue
        probe = f"{label} {p.path}".lower().replace("-", " ").replace("_", " ")
        score = max((w for kw, w in POLICY_LINK_WORDS if kw in probe), default=0)
        if score == 0:
            continue
        if root and root not in (p.hostname or ""):
            score -= 2   # external hosts are less likely to be the site's own policy
        seen.add(full)
        ranked.append((score, full))
    ranked.sort(key=lambda x: -x[0])
    return [u for _, u in ranked]


def fetch_policy(raw_url):
    """
    Finds and reads the privacy policy for a website link.
    Returns dict(text, sources, site_name, note).
    """
    url = normalize_url(raw_url)
    host = urllib.parse.urlparse(url).hostname
    site_name = site_name_from_host(host)
    sources, texts, notes = [], [], []

    final_url, html = _http_get(url)
    text, links, title = html_to_text(html)

    if _looks_like_policy(text, final_url):
        texts.append(text)
        sources.append({"url": final_url, "title": title or "Policy page"})
    else:
        # The link is probably a home page: follow its privacy and terms links.
        candidates = _rank_policy_links(final_url, links)
        base = f"{urllib.parse.urlparse(final_url).scheme}://{urllib.parse.urlparse(final_url).netloc}"
        for path in COMMON_POLICY_PATHS:
            full = base + path
            if full not in candidates:
                candidates.append(full)
        tried = 0
        for cand in candidates:
            if len(sources) >= 2 or tried >= 8:
                break
            tried += 1
            try:
                f_url, c_html = _http_get(cand)
            except AnalysisError:
                continue
            c_text, _, c_title = html_to_text(c_html)
            if _looks_like_policy(c_text, f_url) and f_url not in [s["url"] for s in sources]:
                texts.append(c_text)
                sources.append({"url": f_url, "title": c_title or "Policy page"})
        if not texts:
            raise AnalysisError(
                f"Could not find a readable privacy policy on {host}. The page may need JavaScript "
                "or block automatic access. Open the policy in your browser and paste its text instead.")
        notes.append("Found by following the site's privacy and terms links.")

    combined = "\n".join(texts)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS]
        notes.append("Very long policy: only the first part was analysed.")
    return {"text": combined, "sources": sources, "site_name": site_name, "note": " ".join(notes)}


def site_name_from_host(host):
    host = (host or "").lower()
    if host == "localhost" or re.fullmatch(r"[\d.]+|[0-9a-f:]+", host or ""):
        return host or "Site"
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "ac") and len(parts[-1]) == 2:
        label = parts[-3]
    elif len(parts) >= 2:
        label = parts[-2]
    else:
        label = parts[0] if parts else "Site"
    return label.capitalize()


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def split_sentences(text):
    out = []
    for line in re.split(r"\n+", text):
        for s in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9\"“(])", line):
            s = " ".join(s.split())
            if 25 <= len(s) <= 600:
                out.append(s)
    return out


def _snippet(text, pattern):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    start = max(0, m.start() - 90)
    end = min(len(text), m.end() + 110)
    s = " ".join(text[start:end].split())
    return ("…" if start else "") + s + ("…" if end < len(text) else "")


def detect_practices(text):
    found = []
    flat = " ".join(text.split())
    for key, kind, label, pattern in PRACTICES:
        snip = _snippet(flat, pattern)
        found.append({"key": key, "kind": kind, "label": label,
                      "present": snip is not None, "evidence": snip})
    return found


def extract_clauses(text, service_name):
    sentences = split_sentences(text)
    if not sentences:
        raise AnalysisError("The policy text was empty or too short to analyse.")
    pre = PrivacyPrefilter()
    pre.train_with_minimal_fixture()
    kept = set(pre.filter_candidates(sentences))
    # The prefilter is trained on 8 sentences, so also keep anything that clearly talks about data.
    candidates = [s for s in sentences if s in kept or PRIVACY_WORDS.search(s)]
    seen, uniq = set(), []
    for s in candidates:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    uniq = uniq[:MAX_CLAUSES]
    if not uniq:
        raise AnalysisError("No privacy-related statements were found in that text.")
    extracted = LLMExtractor(service_name=service_name).extract(uniq)
    validate_extraction_output(extracted)
    return extracted, len(sentences)


_SEVERITY_BOOST = re.compile(
    r"\b(sell|sold|share\w*|disclos\w*|third[- ]part\w+|advertis\w+|partners?|affiliates?|"
    r"profil\w+|track\w*|indefinite\w*|without (your )?(consent|notice))\b", re.I)


def heuristic_scores(text, canonical_entities):
    """Content-based severity and specificity (1-5) used only in offline demo mode."""
    top_weight = max((ENTITY_WEIGHT.get(e, 2) for e in canonical_entities), default=1)
    sev = top_weight - 1 + (1 if _SEVERITY_BOOST.search(text) else 0) + 1
    sev = max(1.0, min(5.0, float(sev)))
    named = [e for e in canonical_entities if e != "General Data"]
    spec = 2.0 + (1.0 if len(named) >= 2 else 0.0) + (1.0 if len(named) >= 4 else 0.0)
    return sev, min(5.0, spec)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def band(rating):
    if rating < 25:
        return "Low"
    if rating < 45:
        return "Moderate"
    if rating < 65:
        return "High"
    return "Very high"


def build_report(service_name, text, sources=None, note="", policy_url=""):
    """Runs the full pipeline on policy text and returns a detailed report dict."""
    extracted, n_sentences = extract_clauses(text, service_name)
    canon = EntityCanonicalizer()
    engine = ScoringEngine()

    is_mock = str(extracted.get("mode", "")).startswith("MOCK")
    clauses = []
    for c in extracted.get("clauses", []):
        ents = []
        for e in c.get("entities", []):
            ce = canon.canonicalize(e)
            if ce and ce not in ents:
                ents.append(ce)
        sev = float(c.get("severity_score") or 0)
        spec = float(c.get("specificity_score") or 0)
        if is_mock:
            # The offline mock extractor assigns placeholder scores that depend on sentence order,
            # which would make site-to-site comparison meaningless. Score from the content instead.
            sev, spec = heuristic_scores(c.get("text", ""), ents)
        clauses.append({
            "text": c.get("text", ""),
            "entities": c.get("entities", []),
            "canonical_entities": ents,
            "severity_score": sev,
            "specificity_score": spec,
            "score": engine.calculate_clause_score(sev, spec),
            "risk_category": c.get("risk_category", ""),
        })

    n = len(clauses)
    raw_score = engine.calculate_service_score_from_clauses(clauses)  # ClauseGuard's own formula (sum)
    mean_score = raw_score / n if n else 0.0
    avg_sev = sum(c["severity_score"] for c in clauses) / n if n else 0.0
    avg_spec = sum(c["specificity_score"] for c in clauses) / n if n else 0.0

    # Entities: how many clauses mention each, and how sensitive it is
    ent_counts = {}
    for c in clauses:
        for e in c["canonical_entities"]:
            ent_counts[e] = ent_counts.get(e, 0) + 1
    entities = sorted(
        ({"name": e, "mentions": k, "weight": ENTITY_WEIGHT.get(e, 2),
          "group": ENTITY_GROUP.get(e, "Other")} for e, k in ent_counts.items()),
        key=lambda x: (-x["weight"], -x["mentions"], x["name"]))

    groups = []
    for g in GROUPS:
        members = [e for e in entities if e["group"] == g]
        groups.append({"group": g, "count": len(members),
                       "exposure": sum(e["weight"] for e in members),
                       "entities": [e["name"] for e in members]})
    max_exposure = sum(ENTITY_WEIGHT.values())
    breadth = sum(e["weight"] for e in entities) / max_exposure

    practices = detect_practices(text)
    risk_found = sum(1 for p in practices if p["kind"] == "risk" and p["present"])
    protect_found = sum(1 for p in practices if p["kind"] == "protect" and p["present"])
    adjust = _clamp((risk_found - protect_found) * PRACTICE_ADJUST, -PRACTICE_ADJUST_CAP, PRACTICE_ADJUST_CAP)

    intensity = mean_score / 10.0   # clause score runs 2..10
    base = 100.0 * (0.5 * intensity + 0.5 * min(breadth * 2.2, 1.0))
    rating = _clamp(base + adjust)

    top = sorted(clauses, key=lambda c: -c["score"])[:6]
    return {
        "service_name": service_name,
        "mode": extracted.get("mode", "UNKNOWN"),
        "policy_url": policy_url or (sources[0]["url"] if sources else ""),
        "sources": sources or [],
        "note": note,
        "rating": round(rating, 1),
        "band": band(rating),
        "raw_score": round(raw_score, 1),
        "clause_count": n,
        "sentences_read": n_sentences,
        "avg_severity": round(avg_sev, 2),
        "avg_specificity": round(avg_spec, 2),
        "mean_clause_score": round(mean_score, 2),
        "breadth": round(breadth, 3),
        "practice_adjustment": adjust,
        "entities": entities,
        "groups": groups,
        "practices": practices,
        "top_clauses": top,
        "clauses": clauses,
        "canonical_entities": sorted(ent_counts),
    }


def analyze_site(raw_url=None, pasted_text=None, name=None):
    """Analyze either a link or pasted policy text. Returns a report."""
    if pasted_text and pasted_text.strip():
        label = (name or "").strip() or (site_name_from_host(urllib.parse.urlparse(normalize_url(raw_url)).hostname)
                                         if raw_url and raw_url.strip() else "Pasted policy")
        text = pasted_text.strip()[:MAX_TEXT_CHARS]
        return build_report(label, text, sources=[{"url": raw_url or "", "title": "Pasted text"}],
                            note="Analysed from pasted text.", policy_url=raw_url or "")
    fetched = fetch_policy(raw_url)
    label = (name or "").strip() or fetched["site_name"]
    return build_report(label, fetched["text"], sources=fetched["sources"], note=fetched["note"])


# --------------------------------------------------------------------------
# Comparison / recommendation
# --------------------------------------------------------------------------
def compare_reports(a, b):
    """Builds the recommendation between two reports (lower rating = more private)."""
    diff = a["rating"] - b["rating"]
    if abs(diff) < 4:
        winner = "tie"
    else:
        winner = "a" if diff < 0 else "b"

    if winner == "tie":
        return {
            "winner": "tie", "confidence": "low",
            "headline": f"{a['service_name']} and {b['service_name']} are about equally private",
            "summary": (f"Their risk ratings are {a['rating']:.0f} and {b['rating']:.0f}, too close to call. "
                        "Choose on features, price or what you already use."),
            "reasons": _tie_reasons(a, b), "difference": round(abs(diff), 1)}

    best, worst = (a, b) if winner == "a" else (b, a)
    gap = abs(diff)
    confidence = "high" if gap >= 15 else "medium" if gap >= 8 else "low"
    reasons = []
    reasons.append(f"Overall risk rating is {best['rating']:.0f}/100 ({best['band'].lower()}) for {best['service_name']} "
                   f"versus {worst['rating']:.0f}/100 ({worst['band'].lower()}) for {worst['service_name']}.")

    best_names = {e["name"] for e in best["entities"]}
    worst_names = {e["name"] for e in worst["entities"]}
    only_worst = sorted(worst_names - best_names, key=lambda n: -ENTITY_WEIGHT.get(n, 2))
    sensitive_only_worst = [n for n in only_worst if ENTITY_WEIGHT.get(n, 2) >= 3]
    if sensitive_only_worst:
        reasons.append(f"{worst['service_name']} also mentions sensitive data that {best['service_name']} does not: "
                       f"{', '.join(sensitive_only_worst[:4])}.")
    elif len(worst_names) > len(best_names):
        reasons.append(f"{worst['service_name']} covers more kinds of data ({len(worst_names)} versus {len(best_names)}).")

    if worst["avg_severity"] - best["avg_severity"] >= 0.3:
        reasons.append(f"Its statements are more severe on average (severity {worst['avg_severity']:.1f} "
                       f"versus {best['avg_severity']:.1f}).")

    wp = {p["key"] for p in worst["practices"] if p["present"] and p["kind"] == "risk"}
    bp = {p["key"] for p in best["practices"] if p["present"] and p["kind"] == "risk"}
    labels = {p["key"]: p["label"] for p in worst["practices"]}
    for k in sorted(wp - bp):
        reasons.append(f"{worst['service_name']}: {labels[k].lower()}. {best['service_name']} shows no sign of this.")
    wprot = {p["key"] for p in worst["practices"] if p["present"] and p["kind"] == "protect"}
    bprot = {p["key"] for p in best["practices"] if p["present"] and p["kind"] == "protect"}
    labels_best = {p["key"]: p["label"] for p in best["practices"]}
    extra_prot = [labels_best[k].lower() for k in sorted(bprot - wprot)]
    if extra_prot:
        reasons.append(f"{best['service_name']} gives users more protection: {'; '.join(extra_prot[:3])}.")

    summary = (f"Use {best['service_name']}. Its privacy policy exposes less of your data "
               f"({best['rating']:.0f} versus {worst['rating']:.0f} on a 0 to 100 risk scale).")
    return {"winner": winner, "confidence": confidence,
            "headline": f"{best['service_name']} is the more private choice",
            "summary": summary, "reasons": reasons[:7], "difference": round(gap, 1)}


def _tie_reasons(a, b):
    out = [f"{a['service_name']} mentions {len(a['entities'])} kinds of data; {b['service_name']} mentions {len(b['entities'])}."]
    pa = sum(1 for p in a["practices"] if p["present"] and p["kind"] == "protect")
    pb = sum(1 for p in b["practices"] if p["present"] and p["kind"] == "protect")
    out.append(f"User protections found: {pa} for {a['service_name']}, {pb} for {b['service_name']}.")
    return out


def portfolio_impact(report, db_path):
    """Marginal risk of adding this service to the saved portfolio (None if there is no portfolio)."""
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        n = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        conn.close()
        if n == 0:
            return None
        from marginal import MarginalRiskEngine
        res = MarginalRiskEngine(db_path).calculate_marginal_risk(
            {"service_name": report["service_name"], "clauses": report["clauses"]})
        return {k: res[k] for k in ("baseline_portfolio_risk", "new_portfolio_risk", "marginal_risk_delta",
                                     "overlapping_entities", "newly_introduced_entities")}
    except Exception:
        return None
