#!/usr/bin/env python3
"""Cut the four faces the reports are set in down to the characters they draw.

Run by hand, once, and again only if the typeface changes. It needs fontTools;
rendering a report does not. tools/report_pdf.py reads only what this writes —
the subset files and their measurements — so a verifier needs nothing but
python3 and this repository to render a report again and compare hashes.

    python3 tools/_make_fonts.py --source DIR

DIR holds the originals, taken from the Google Fonts repository at
https://raw.githubusercontent.com/google/fonts/main/ofl/:

    newsreader/Newsreader[opsz,wght].ttf       saved as Newsreader-var.ttf
    geistmono/GeistMono[wght].ttf              saved as GeistMono-var.ttf
    newsreader/OFL.txt                         saved as OFL-newsreader.txt
    geistmono/OFL.txt                          saved as OFL-geist-mono.txt

Each is checked against the hash pinned below, so a later rebuild starts from
the same bytes. Both families are published under the SIL Open Font License,
under different copyrights, so both licences are copied beside the fonts, as
they require.

Everything a reader reads is set in Newsreader, as on the site: the prose, the
labels, the headings and the figures, whose default numerals are lining and
tabular, so a column of them aligns with no feature applied. What a reader
copies, a hash or a file's name, is set in Geist Mono. Both sources are
variable fonts, so each face is pinned first (instancing) — to its weight, and
to a text optical size where the face offers one — and cut afterwards.
Nothing is timestamped: building twice gives the same bytes.

It writes tools/fonts/*.ttf, tools/fonts/OFL.txt and tools/font_metrics.py.
"""

import argparse
import hashlib
import io
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(HERE, "fonts")

# role, source file, weight to pin (None when the source is already one weight),
# and the characters it carries: all of WinAnsi, or ASCII alone for the mono, which
# sets only what a reader copies (a hash, a file's name) and lacks some of WinAnsi.
FACES = [
    ("serif-regular", "Newsreader-var.ttf", 400, "winansi"),
    ("serif-medium", "Newsreader-var.ttf", 500, "winansi"),
    ("serif-semibold", "Newsreader-var.ttf", 600, "winansi"),
    ("mono-regular", "GeistMono-var.ttf", 400, "ascii"),
]
SERIF = {"Newsreader-var.ttf"}                     # the faces a reader is told have serifs
SOURCES = {
    "Newsreader-var.ttf": "8a08d13f8a6c0d51be379a60af84f945f65369a67e509ee3c3bdcc421254d7c1",
    "GeistMono-var.ttf": "d00e590b8eb3a59acc329b2d044fd143ae935090b7da33199ebee27cc7de8196",
    "OFL-newsreader.txt": "fdfad38143ec470553cae82a1e45320bdd1b9ec70415d37bd0171051d8a4ded8",
    "OFL-geist-mono.txt": "1781d2806a07d91c4edf4740b88449fab7d0eadad53f7c351b94cd4d4eb8c00f",
}
LICENCES = ["OFL-newsreader.txt", "OFL-geist-mono.txt"]

# A face drawn for text, where the source has an optical size to choose from:
# the reports set their prose at nine and a half points.
TEXT_SIZE = 10

# The reports are drawn with WinAnsi, the encoding every PDF reader knows: the
# bytes 32 to 255 that cp1252 defines, less 127, which is a control code. The
# minus sign is not in that set and a report is full of them, so it takes 127.
MINUS = 0x2212
MINUS_CODE = 127
FIRST_CODE = 32


def winansi():
    """{byte code: character} for the encoding the reports are drawn with."""
    table = {}
    for code in range(FIRST_CODE, 256):
        if code == MINUS_CODE:
            continue
        try:
            table[code] = ord(bytes([code]).decode("cp1252"))
        except UnicodeDecodeError:
            pass
    table[MINUS_CODE] = MINUS
    return table


def charset(name, table):
    """The part of `table` a face carries: all of it, or its printable ASCII and the minus sign."""
    if name == "winansi":
        return table
    return {code: u for code, u in table.items() if 32 <= u < 127 or u == MINUS}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def cut(source, weight, wanted):
    """The subset of one face, as bytes, with its measurements."""
    font = TTFont(source, recalcTimestamp=False)
    if weight is not None:
        # Only the axes this face has: a width it does not offer is not a value
        # to ask for, and an optical size is set for text.
        settings = {"wght": weight, "opsz": TEXT_SIZE}
        axes = {a.axisTag: settings.get(a.axisTag, a.defaultValue) for a in font["fvar"].axes}
        # The name table is left as it is: Newsreader states no name for a text optical
        # size, and a report names its faces by role, never by what a font calls itself.
        font = instancer.instantiateVariableFont(font, axes, inplace=True, updateFontNames=False)
    absent = [f"U+{u:04X}" for u in sorted(set(wanted.values())) if u not in font.getBestCmap()]
    if absent:
        raise SystemExit(f"{os.path.basename(source)} cannot draw {', '.join(absent)}")

    options = subset.Options()
    options.layout_features = []          # no kerning or ligatures: the writer places every run itself
    options.hinting = False               # a PDF reader does its own hinting
    # The glyph names stay: a reader looks up the minus sign by name, because it
    # sits at a code WinAnsi gives to something else.
    options.glyph_names = True
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]     # the copyright and licence stay
    options.name_legacy = False
    options.drop_tables += ["DSIG"]
    cutter = subset.Subsetter(options=options)
    cutter.populate(unicodes=sorted(set(wanted.values())))
    cutter.subset(font)

    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    head, hhea, os2 = font["head"], font["hhea"], font["OS/2"]
    cap = getattr(os2, "sCapHeight", 0) or font["glyf"]["H"].yMax
    # A PDF states every measure in thousandths of the size, whatever the grid the
    # face is drawn on (Newsreader's is 2000 to the em, Geist Mono's 1000).
    k = 1000 / head.unitsPerEm
    measured = {
        "flags": 32 | (1 if os2.panose.bProportion == 9 else 0) | (2 if os.path.basename(source) in SERIF else 0),
        "bbox": [round(v * k) for v in (head.xMin, head.yMin, head.xMax, head.yMax)],
        "ascent": round(hhea.ascent * k), "descent": round(hhea.descent * k), "cap_height": round(cap * k),
        "italic_angle": round(font["post"].italicAngle),
        # Readers use the stem width only to pick a stand-in face, which cannot
        # happen for a font that is embedded. This is the usual approximation.
        "stem_v": round(50 + (os2.usWeightClass / 65.0) ** 2),
        "widths": [round(hmtx[cmap[wanted[code]]][0] * k) if code in wanted else 0
                   for code in range(FIRST_CODE, 256)],
    }
    font.recalcTimestamp = False
    out = io.BytesIO()
    font.save(out)
    return out.getvalue(), measured


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, metavar="DIR", help="the originals named above")
    a = ap.parse_args()

    for name, pinned in SOURCES.items():
        path = os.path.join(a.source, name)
        if not os.path.exists(path):
            raise SystemExit(f"{name} is not in {a.source}")
        with open(path, "rb") as f:
            found = digest(f.read())
        if found != pinned:
            raise SystemExit(f"{name} is not the pinned original: {found}")

    wanted = winansi()
    os.makedirs(FOLDER, exist_ok=True)
    faces = {}
    for role, source, weight, chars in FACES:
        carried = charset(chars, wanted)
        data, measured = cut(os.path.join(a.source, source), weight, carried)
        again, _ = cut(os.path.join(a.source, source), weight, carried)
        if data != again:
            raise SystemExit(f"{role} does not come out the same twice")
        with open(os.path.join(FOLDER, role + ".ttf"), "wb") as f:
            f.write(data)
        measured["sha256"] = digest(data)
        faces[role] = measured
        print(f"{role:15s} {len(data) / 1024:6.1f} KB  {measured['sha256'][:16]}")

    for name in LICENCES:
        with open(os.path.join(a.source, name), "rb") as f:
            licence = f.read()
        with open(os.path.join(FOLDER, name), "wb") as f:
            f.write(licence)

    lines = [
        '"""The measurements of the faces in tools/fonts, written by tools/_make_fonts.py.',
        "",
        "Every width is in thousandths of the font size, as a PDF states them. The codes",
        f"run from {FIRST_CODE} to 255 and are WinAnsi, except {MINUS_CODE}, which is the minus sign.",
        'Do not edit: run the tool again.',
        '"""',
        "",
        f"FIRST_CODE = {FIRST_CODE}",
        f"MINUS_CODE = {MINUS_CODE}",
        "UNITS_PER_EM = 1000",
        "",
        "FACES = {",
    ]
    for role in sorted(faces):
        face = faces[role]
        lines.append(f'    "{role}": {{')
        lines.append(f'        "sha256": "{face["sha256"]}",')
        for key in ("flags", "ascent", "descent", "cap_height", "italic_angle", "stem_v"):
            lines.append(f'        "{key}": {face[key]},')
        lines.append(f'        "bbox": {face["bbox"]},')
        lines.append('        "widths": [')
        row = face["widths"]
        for start in range(0, len(row), 16):
            lines.append("            " + " ".join(f"{w}," for w in row[start:start + 16]))
        lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    with open(os.path.join(HERE, "font_metrics.py"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"written: tools/fonts/*.ttf ({len(faces)}), "
          + ", ".join("tools/fonts/" + name for name in LICENCES) + ", tools/font_metrics.py")


if __name__ == "__main__":
    main()
