"""Make every source and doc file plain ASCII.

A PowerShell `Get-Content`/`Set-Content` round-trip double-encoded the punctuation
in three analysis scripts, and repeated repairs kept re-introducing it. Rather
than chase the encoding, this strips non-ASCII from the code and docs: the only
non-ASCII characters ever used there were em dashes and curly quotes, and both
have plain equivalents. ASCII-only source, no dependence on console encoding.
"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent
targets = (list(root.glob("analysis/*.py")) + list(root.glob("ingest/*.py"))
           + list(root.glob("spike/*.py")) + list(root.glob("*.md"))
           + list(root.glob("*.py")))

DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
QUOTES = "\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f"

for p in targets:
    t = p.read_text(encoding="utf-8", errors="replace")
    t = t.lstrip("\ufeff")
    orig = t
    # collapse any residual mojibake first, then map the real characters
    t = re.sub(r"includes zero, not distinguishable",
               "includes zero, not distinguishable", t)
    for ch in DASHES:
        t = t.replace(ch, "-")
    for ch in QUOTES:
        t = t.replace(ch, '"')
    t = t.replace("\u00a0", " ")
    # anything still non-ASCII: keep its base letter if it has one, else drop
    if any(ord(c) > 127 for c in t):
        out = []
        for c in t:
            if ord(c) < 128:
                out.append(c)
            else:
                base = c.encode("ascii", "ignore").decode("ascii")
                out.append(base)
        t = "".join(out)
    if t != orig:
        p.write_text(t, encoding="utf-8")
        print(f"cleaned {p.relative_to(root)}")

leftover = [(p.name, ord(c)) for p in targets
            for c in p.read_text(encoding="utf-8", errors="replace") if ord(c) > 127]
print("non-ascii left:", leftover[:5] or "none")
