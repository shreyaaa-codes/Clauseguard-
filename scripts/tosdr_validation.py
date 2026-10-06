"""
Validate ClauseGuard against ToS;DR (https://tosdr.org) community ratings.

Run from the repo root:
    python scripts/tosdr_validation.py            # fetch (cached) + compare
    python scripts/tosdr_validation.py --offline  # use cache only

Inputs
  * SERVICES below (domain -> display name, category)
  * data/raw/<domain>.txt  : policy text you pasted (same files ClauseGuard analyses)
Outputs
  * data/evaluation/tosdr_cache/<domain>.json   raw ToS;DR responses (reproducibility)
  * data/evaluation/tosdr_validation.json       all numbers for the report
  * a printed summary table

What it measures
  1. Ranking agreement: ClauseGuard rating (higher = riskier) vs ToS;DR grade
     (A best .. E worst), Spearman rho with tie handling.
  2. Practice agreement: for each practice ClauseGuard detects (sells_data, third_party...),
     does ToS;DR have a matching 'bad/blocker' point? Reported as precision/recall/F1 and
     pooled Cohen's kappa. ToS;DR only lists what its volunteers noticed, so treat
     recall as the more meaningful number and precision as a lower bound.
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CACHE = os.path.join(ROOT, "data", "evaluation", "tosdr_cache")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "evaluation", "tosdr_validation.json")
API = "https://api.tosdr.org"

# EDIT THIS LIST: domain -> (display name, category). Domain must match data/raw/<domain>.txt
SERVICES = {
    "spotify.com":   ("Spotify", "streaming"),
    "netflix.com":   ("Netflix", "streaming"),
    "whatsapp.com":  ("WhatsApp", "messaging"),
    "telegram.org":  ("Telegram", "messaging"),
    "instagram.com": ("Instagram", "social"),
    "swiggy.com":    ("Swiggy", "food"),
    "zomato.com":    ("Zomato", "food"),
    "phonepe.com":   ("PhonePe", "payments"),
    "paytm.com":     ("Paytm", "payments"),
    "uber.com":      ("Uber", "mobility"),
    "coursera.org":  ("Coursera", "education"),
}

GRADE_RANK = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}

# ToS;DR case title keywords -> ClauseGuard practice key.
# RISK practices count when the ToS;DR point is 'bad' or 'blocker'.
# PROTECT practices count when the point is 'good'.
RISK_MAP = {
    "sells_data": r"\bsell|\bsold\b|monetis|monetiz",
    "ad_sharing": r"advertis",
    "third_party": r"third[- ]part|shared with|shares? (your )?(personal )?(data|information)|affiliates",
    "long_retention": r"retain|retention|kept|stored (for|indefinitely)|indefinite|undefined|unspecified",
    "profiling": r"profil|automated|personali[sz]ed|inferen|behaviou?ral",
    "arbitration": r"arbitration|class action",
    "content_license": r"licen[cs]e",
    "unilateral_changes": r"(terms|policy|agreement|conditions)[^.]{0,40}(chang|modif|updat|amend)|(chang|modif|updat|amend)[^.]{0,40}(terms|policy|agreement|conditions)",
    "cross_border": r"transfer|outside|other countr|international",
}
PROTECT_MAP = {
    "delete_right": r"delet|erase|erasure|removal",
    "opt_out": r"opt[- ]?out",
    "no_sale": r"not (be )?sold|does not sell|never sell",
}
# A ToS;DR title matching these does NOT count for the practice (e.g. a bankruptcy/merger
# transfer is not 'selling data to third parties'; deleting YOUR account is not a protection).
EXCLUDE = {
    "sells_data": r"bankruptcy|merger|acquisition|financial transaction|business transfer",
    "cross_border": r"bankruptcy|merger|acquisition|financial transaction",
    "third_party": r"bankruptcy|merger|acquisition|financial transaction",
}
# Practices that normally live in the Terms of Service, not the privacy policy. They are only
# evaluated for a service if you also saved data/raw/<domain>_terms.txt.
TERMS_ONLY = {"arbitration", "content_license", "unilateral_changes"}
# ToS;DR tracking points: ClauseGuard has no tracking/cookie practice, so these are reported
# as a coverage gap instead of being scored against 'profiling'.
TRACKING = r"track|cookie|pixel|beacon|fingerprint"


# ---------------------------------------------------------------- ToS;DR fetching
def _get(url, retries=5):
    req = urllib.request.Request(url, headers={"User-Agent": "ClauseGuard-student-eval/1.0",
                                               "Accept": "application/json"})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network / rate limit
            last = e
            wait = 6 * (i + 1) if "429" in str(e) else 1.5 * (i + 1)
            time.sleep(wait)
    raise RuntimeError(f"GET {url} failed: {last}")


def _host(u):
    u = re.sub(r"^https?://", "", str(u).lower())
    return re.sub(r"^www\.", "", u).split("/")[0]


def find_service(domain, name):
    """Search ToS;DR and pick the service whose URL list contains the domain."""
    services = []
    for term in (name, domain, domain.split(".")[0]):
        data = _get(f"{API}/search/v5/?query={urllib.parse.quote(term)}")
        services = data.get("services") or data.get("parameters", {}).get("services") or []
        time.sleep(1.5)
        if any(_host(u) == domain for s in services for u in s.get("urls", [])):
            break
    for s in services:
        if any(_host(u) == domain for u in s.get("urls", [])):
            return s
    for s in services:  # looser: same registrable name
        if domain.split(".")[0] in [_host(u).split(".")[0] for u in s.get("urls", [])]:
            return s
    return None


def fetch(domain, name, offline=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{domain}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if offline:
        return None
    hit = find_service(domain, name)
    if not hit:
        rec = {"domain": domain, "found": False}
    else:
        time.sleep(1.5)
        svc = _get(f"{API}/service/v3/?id={hit['id']}")
        rec = {"domain": domain, "found": True, "fetched": time.strftime("%Y-%m-%d"), "service": svc}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return rec


def tosdr_facts(rec):
    """Reduce a cached ToS;DR record to grade + set of practices."""
    if not rec or not rec.get("found"):
        return None
    svc = rec["service"]
    grade = str(svc.get("rating", "")).strip().upper()
    risk, protect, titles, why, tracking = set(), set(), [], {}, 0
    for p in svc.get("points", []):
        if p.get("status") and p["status"] != "approved":
            continue
        case = p.get("case") or {}
        cls, title = case.get("classification"), (case.get("title") or p.get("title") or "")
        titles.append({"title": title, "classification": cls, "weight": case.get("weight")})
        if cls in ("bad", "blocker") and re.search(TRACKING, title, re.I):
            tracking += 1
        if cls in ("bad", "blocker"):
            for k, pat in RISK_MAP.items():
                if k in EXCLUDE and re.search(EXCLUDE[k], title, re.I):
                    continue
                if re.search(pat, title, re.I):
                    risk.add(k)
                    why.setdefault(k, []).append(title)
        elif cls == "good":
            for k, pat in PROTECT_MAP.items():
                if re.search(pat, title, re.I):
                    protect.add(k)
                    why.setdefault(k, []).append(title)
    return {"grade": grade if grade in GRADE_RANK else None, "risk": risk,
            "protect": protect, "n_points": len(titles), "points": titles, "why": why, "tracking": tracking}


# ---------------------------------------------------------------- statistics
def _avg_ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks, i = [0.0] * len(xs), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = _avg_ranks(a), _avg_ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return None if den == 0 else num / den


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def cohen_kappa(pairs):
    n = len(pairs)
    if n == 0:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


# ---------------------------------------------------------------- main
def clauseguard_report(domain, name):
    path = os.path.join(RAW, f"{domain}.txt")
    if not os.path.exists(path):
        return None
    from src.analyzer import build_report
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    tpath = os.path.join(RAW, f"{domain}_terms.txt")
    has_terms = os.path.exists(tpath)
    if has_terms:
        with open(tpath, encoding="utf-8", errors="ignore") as f:
            text += "\n" + f.read()
    rep = build_report(name, text)
    rep["_terms_included"] = has_terms
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached ToS;DR data only")
    ap.add_argument("--debug", action="store_true", help="list every disagreement with its evidence")
    args = ap.parse_args()

    rows, skipped = [], []
    for domain, (name, cat) in SERVICES.items():
        facts = None
        try:
            facts = tosdr_facts(fetch(domain, name, args.offline))
        except Exception as e:
            skipped.append((domain, f"ToS;DR fetch error: {e}"))
            continue
        rep = clauseguard_report(domain, name)
        if rep is None:
            skipped.append((domain, f"missing data/raw/{domain}.txt"))
            continue
        if facts is None:
            skipped.append((domain, "not found on ToS;DR"))
            continue
        cg_present = {p["key"] for p in rep["practices"] if p["present"]}
        rows.append({"domain": domain, "name": name, "category": cat,
                     "cg_rating": rep["rating"], "cg_band": rep["band"],
                     "tosdr_grade": facts["grade"], "tosdr_points": facts["n_points"],
                     "tosdr_risk": sorted(facts["risk"]), "tosdr_protect": sorted(facts["protect"]),
                     "cg_practices": sorted(cg_present), "terms_included": rep["_terms_included"],
                     "tosdr_tracking_points": facts["tracking"], "tosdr_why": {k: v[:3] for k, v in facts["why"].items()},
                     "cg_evidence": {p["key"]: p["evidence"] for p in rep["practices"] if p["present"]}})

    graded = [r for r in rows if r["tosdr_grade"]]
    result = {"generated": time.strftime("%Y-%m-%d"), "n_services_compared": len(rows),
              "n_graded": len(graded), "skipped": skipped, "services": rows}

    # 1. ranking agreement
    rho = spearman([r["cg_rating"] for r in graded], [GRADE_RANK[r["tosdr_grade"]] for r in graded])
    result["spearman_rho"] = None if rho is None else round(rho, 3)

    # 2. practice agreement (only services ToS;DR has points for)
    per, pooled, pooled_by, pos_count = {}, [], {}, {}
    covered = [r for r in rows if r["tosdr_points"] > 0]
    for key in list(RISK_MAP) + list(PROTECT_MAP):
        tp = fp = fn = 0
        for r in covered:
            if key in TERMS_ONLY and not r["terms_included"]:
                continue
            truth = key in (r["tosdr_risk"] if key in RISK_MAP else r["tosdr_protect"])
            pred = key in r["cg_practices"]
            pooled.append((int(pred), int(truth)))
            pooled_by.setdefault(key, []).append((int(pred), int(truth)))
            pos_count[key] = pos_count.get(key, 0) + int(truth)
            tp += pred and truth
            fp += pred and not truth
            fn += truth and not pred
        if tp + fp + fn:
            p, rc, f = prf(tp, fp, fn)
            per[key] = {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3),
                        "recall": round(rc, 3), "f1": round(f, 3)}
    k = cohen_kappa(pooled)
    result["practice_agreement"] = per
    result["pooled_cohen_kappa"] = None if k is None else round(k, 3)
    # practices for which ToS;DR has at least one matching point anywhere in the sample
    comparable = [kk for kk, c in pos_count.items() if c >= 1]
    not_comparable = [kk for kk in pooled_by if kk not in comparable]
    kc = cohen_kappa([x for kk in comparable for x in pooled_by[kk]])
    result["comparable_practices"] = comparable
    result["no_tosdr_counterpart"] = not_comparable
    result["pooled_cohen_kappa_comparable"] = None if kc is None else round(kc, 3)
    tp_all = sum(v["tp"] for v in per.values()); fn_all = sum(v["fn"] for v in per.values())
    fp_all = sum(v["fp"] for v in per.values())
    result["micro_recall"] = round(tp_all / (tp_all + fn_all), 3) if tp_all + fn_all else None
    result["micro_precision_lower_bound"] = round(tp_all / (tp_all + fp_all), 3) if tp_all + fp_all else None
    result["coverage_gap_tracking_points"] = sum(r["tosdr_tracking_points"] for r in rows)
    result["terms_only_practices_skipped_without_terms_file"] = sorted(TERMS_ONLY)
    result["notes"] = ("ToS;DR grades rate fairness of terms and privacy policy combined and are "
                       "community-curated; absent ToS;DR points do not prove a practice is absent, "
                       "so precision is a lower bound.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)

    # printed summary
    print(f"\n{'service':<12}{'ClauseGuard':>12}{'band':>11}{'ToS;DR':>8}")
    for r in sorted(rows, key=lambda r: -r["cg_rating"]):
        print(f"{r['name']:<12}{r['cg_rating']:>12}{r['cg_band']:>11}{(r['tosdr_grade'] or '-'):>8}")
    print(f"\nServices compared: {len(rows)} (graded by ToS;DR: {len(graded)})")
    print(f"Spearman rho (ClauseGuard vs ToS;DR grade): {result['spearman_rho']}")
    print(f"Pooled Cohen's kappa on practices: {result['pooled_cohen_kappa']}")
    print(f"  ...only practices ToS;DR has a counterpart for: {result['pooled_cohen_kappa_comparable']}  "
          f"(no ToS;DR counterpart: {result['no_tosdr_counterpart']})")
    print(f"Micro recall (ToS;DR-flagged practices ClauseGuard also found): {result['micro_recall']}")
    print(f"Micro precision (lower bound): {result['micro_precision_lower_bound']}")
    for key, v in per.items():
        print(f"  {key:<20} P={v['precision']:.2f} R={v['recall']:.2f} F1={v['f1']:.2f}  (tp={v['tp']} fp={v['fp']} fn={v['fn']})")
    print(f"ToS;DR tracking/cookie points across these services (ClauseGuard has no such practice): "
          f"{result['coverage_gap_tracking_points']}")
    print(f"Terms-only practices {sorted(TERMS_ONLY)} are scored only for services with data/raw/<domain>_terms.txt")
    for d, why in skipped:
        print(f"SKIPPED {d}: {why}")
    if args.debug:
        print("\n===== DISAGREEMENTS (check these by hand before quoting kappa) =====")
        for r in rows:
            for key in list(RISK_MAP) + list(PROTECT_MAP):
                if key in TERMS_ONLY and not r["terms_included"]:
                    continue
                truth = key in (r["tosdr_risk"] if key in RISK_MAP else r["tosdr_protect"])
                pred = key in r["cg_practices"]
                if truth and not pred:
                    print(f"\n[{r['name']}] {key}: ToS;DR says yes, ClauseGuard says NO")
                    for t in r["tosdr_why"].get(key, []):
                        print(f"   ToS;DR point: {t}")
                elif pred and not truth and r["tosdr_points"] > 0:
                    print(f"\n[{r['name']}] {key}: ClauseGuard says YES, ToS;DR has no matching point")
                    print(f"   ClauseGuard evidence: {(r['cg_evidence'].get(key) or '')[:200]}")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()