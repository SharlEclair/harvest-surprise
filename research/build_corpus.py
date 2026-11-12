"""Build the full comment corpus and a first-pass taxonomy.

Reads a yt-dlp metadata dump of the video (not committed: it holds third-party comment
data; fetch it with `yt-dlp --write-comments --skip-download --write-info-json`), writes
research/comments_all.csv (every comment, root and reply, commenter handles replaced by
stable pseudonyms) and prints the keyword taxonomy that drives the research queue.

The taxonomy is deliberately crude - it is a recall device, not a classifier.
Anything it misses is caught by reading the unmatched tail.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT
KEEP = {"@losingloonies"}  # the video's creator, credited by name
HANDLE = re.compile(r"@[\w.\-]{3,}")


def pseudo(text):
    """Replace every @handle with a stable pseudonym (sha1 prefix), except the creator."""
    def one(m):
        h = m.group(0)
        return h if h.lower() in KEEP else "@user-" + hashlib.sha1(h.lower().encode()).hexdigest()[:6]
    return HANDLE.sub(one, text or "")

TAXONOMY = {
    "oil_tanks": r"\btank(s)?\b|floating roof|cushing|fill level|oil storage",
    "vessels": r"\bship(s)?\b|vessel|tanker|ais\b|cargo|freighter|boat|docking|anchorage",
    "ports_containers": r"\bport(s)?\b|container|terminal|dock|crane",
    "parking_retail": r"\bparking|cars?\b|walmart|retail|store|shoppers|footfall",
    "agriculture": r"\bcrop|corn|soy|wheat|harvest|yield|farm|agri|ndvi|vegetation",
    "mining_materials": r"\bmine|mining|ore|copper|lithium|bauxite|quarry|smelter",
    "construction": r"\bconstruction|building site|crane|housing|property|real estate",
    "water": r"\breservoir|dam\b|water level|lake|drought|river|aquifer",
    "energy": r"\bflare|flaring|power plant|solar farm|wind farm|turbine|refinery|gas\b",
    "fire": r"\bwildfire|fire\b|burn|smoke",
    "nightlights": r"\bnight ?light|viirs|light pollution|electricity|blackout",
    "transport": r"\btruck(s)?\b|train(s)?\b|rail|freight|traffic|highway|lane",
    "aircraft": r"\bplane(s)?\b|aircraft|airport|flight",
    "retail_stock": r"\bearnings|revenue|stock|ticker|hedge|quant|trading",
    "methods_sar": r"\binsar|sar\b|radar|interferometr|sentinel-1",
    "methods_res": r"resolution|super.?res|subpixel|pixel|metre|meter|10 ?m|3 ?m",
    "methods_ml": r"\bmachine learning|\bml\b|neural|model|training|dataset",
    "methods_cloud": r"\bcloud(s)?\b|weather|haze|atmospher",
    "data_sources": r"planet|airbus|sentinel|landsat|modis|google maps|commercial",
}


def main() -> int:
    src = ROOT / "VJm9BBJwMDY.info.json"
    if not src.exists():
        src = ROOT.parent / "VJm9BBJwMDY.info.json"
    meta = json.loads(src.read_text(encoding="utf-8"))
    comments = meta.get("comments") or []
    print(f"comments: {len(comments)}")

    rows = []
    by_id = {c["id"]: c for c in comments}
    for c in comments:
        parent = c.get("parent") or "root"
        rows.append({
            "id": c["id"],
            "author": pseudo(c.get("author")),
            "likes": c.get("like_count") or 0,
            "is_reply": parent != "root",
            "parent_id": "" if parent == "root" else parent,
            "parent_author": pseudo(by_id.get(parent, {}).get("author", "")) if parent != "root" else "",
            "text": pseudo(" ".join((c.get("text") or "").split())),
        })
    rows.sort(key=lambda r: (-r["likes"], r["id"]))
    import csv
    OUT.mkdir(exist_ok=True)
    with (OUT / "comments_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    roots = [r for r in rows if not r["is_reply"]]
    replies = [r for r in rows if r["is_reply"]]
    print(f"root {len(roots)}, replies {len(replies)}")

    hits = defaultdict(list)
    for r in rows:
        for name, pat in TAXONOMY.items():
            if re.search(rf"\b(?:{pat})\b", r["text"], re.I):
                hits[name].append(r)

    print("\n=== taxonomy (comments matching, unique) ===")
    for name, rs in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        top = max(rs, key=lambda r: r["likes"])
        print(f"{name:18s} {len(rs):4d}  top[{top['likes']:4d}] {top['text'][:110]}")

    matched = {r["id"] for rs in hits.values() for r in rs}
    unmatched = [r for r in rows if r["id"] not in matched]
    print(f"\nunmatched: {len(unmatched)}")
    for r in unmatched[:15]:
        print(f"  [{r['likes']:3d}] {r['text'][:130]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
