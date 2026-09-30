"""The PDF of a report, laid out from its Markdown (Methodology, section 5).

The layout is done here, and it follows the public site: the record set as a
paper. A head that states the programme and its terms, sections whose heading
sits on a rule, prose at a reading measure, figures right aligned in their
column in the text face's tabular numerals, hairlines instead of boxes. Colour carries
information and nothing else: the brand green marks the full stop of the name,
the number of a section and a gain; the loss colour a loss; a grey of its own
the benchmark. A figure with no direction in it stays in the ink of the page.

Everything a reader reads is set in Newsreader, as on the site, and what a
reader copies (a hash, a file's name) in Geist Mono. The four faces are cut by
tools/_make_fonts.py and embedded whole, once each,
from tools/fonts, with their measurements read from tools/font_metrics.py. The
file carries no date and nothing is compressed, so the same Markdown gives the
same PDF, byte for byte: a verifier renders the Markdown again and compares
hashes, needing nothing but python3 and this repository.

Only what the report generators write is read: a title, paragraphs, list items,
tables, rules, bold and code spans. Anything else stops the rendering rather
than being drawn wrongly, as does a character the faces cannot draw.
"""

import os
import re

import font_metrics as metrics

PAGE_W, PAGE_H = 595.28, 841.89                    # A4, in points
LEFT = RIGHT = 56.0
TOP, BOTTOM = 52.0, 74.0
WIDTH = PAGE_W - LEFT - RIGHT
MEASURE = 440.0                                    # prose is read at about 95 characters, nearer the tables' edge
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# The site's ink and paper (brand tokens), as PDF grey and colour.
INK = (0.059, 0.110, 0.090)                        # #0F1C17
MUTED = (0.294, 0.353, 0.329)                      # #4B5A54
FAINT = (0.525, 0.580, 0.561)                      # #86948F
RULE = (0.882, 0.906, 0.894)                       # #E1E7E4
RULE_STRONG = (0.761, 0.804, 0.784)                # #C2CDC8
GREEN = (0.059, 0.639, 0.498)
LOSS = (0.612, 0.200, 0.157)
BENCHMARK = (0.663, 0.651, 0.620)                  # bitcoin, bought and held

# The roles the writer draws in, and the face each is set in. The figures take the
# text face: its default numerals are lining and tabular, so a column aligns.
ROLES = {"text": "serif-regular", "text-bold": "serif-semibold",
         "label": "serif-regular", "label-bold": "serif-medium",
         "figure": "serif-regular", "code": "mono-regular"}
# The faces, each embedded once, in the order their resources are numbered.
EMBEDDED = ["serif-regular", "serif-semibold", "serif-medium", "mono-regular"]
RESOURCE = {role: f"F{EMBEDDED.index(face) + 1}" for role, face in ROLES.items()}
BOLDER = {"text": "text-bold", "label": "label-bold", "figure": "figure", "code": "code",
          "text-bold": "text-bold", "label-bold": "label-bold"}

# The minus sign is not in WinAnsi and a report is full of them, so the faces
# carry it at the one code WinAnsi leaves for a control character.
TRANSLATE = {"−": chr(metrics.MINUS_CODE)}

# size, leading, space before, space after
STYLE = {"title": (17.0, 21.0, 0.0, 0.0), "h2": (9.6, 13.0, 19.0, 8.0), "h3": (9.0, 12.0, 12.0, 4.0),
         "p": (9.4, 13.6, 0.0, 7.5), "li": (9.4, 13.6, 0.0, 3.0), "note": (7.8, 11.0, 0.0, 5.0),
         "table": (7.9, 10.8, 3.0, 11.0)}
NUMERIC = re.compile(r"[+\-−]?\d[\d,.]*%?|—")
CLINGING = ",.;:!?%)]}"                            # marks that may not begin a line
PAD = 7.0
WORDMARK_TRACKING = -0.02
# Where a reader checks a report: the record's repository and the site's page of
# checks, stated among the terms at the head of every report (the generators write
# them from here). A published report is final, so these are addresses reout keeps:
# its official channels (Disclosure, section 5). Written as a code span, either one
# is drawn as a link.
VERIFY = [("The record", "github.com/reouthq/track", "https://github.com/reouthq/track"),
          ("How to check it", "reout.io/verify", "https://reout.io/verify/")]
LINKS = {shown: uri for _, shown, uri in VERIFY}


def refuse(message):
    raise SystemExit(f"{message}; the report is not produced")


# --- text -------------------------------------------------------------------

def encode(text):
    """The bytes of `text` in the encoding the faces are drawn with."""
    text = "".join(TRANSLATE.get(ch, ch) for ch in text)
    try:
        data = text.encode("cp1252")
    except UnicodeEncodeError as e:
        refuse(f"the character {text[e.start]!r} is not one the faces carry")
    if any(b < metrics.FIRST_CODE and b != metrics.MINUS_CODE for b in data):
        refuse(f"a control character in {text[:40]!r}")
    return data


def escape(data):
    out = []
    for b in data:
        if b in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(b))
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\{b:03o}")
    return "".join(out)


def advance(role, text, size, tracking=0.0):
    """How far the drawing point moves, in points."""
    widths = metrics.FACES[ROLES[role]]["widths"]
    data = encode(text)
    # A face carries no width for a character it lacks: the mono carries ASCII alone.
    if any(widths[b - metrics.FIRST_CODE] == 0 for b in data):
        refuse(f"{text[:40]!r} has a character the {ROLES[role]} face does not carry")
    total = sum(widths[b - metrics.FIRST_CODE] for b in data) * size / metrics.UNITS_PER_EM
    return total + tracking * size * len(data)


def spans(text, role):
    """[(role, text)]: code spans in the code face, bold spans in the bold face, the rest in `role`."""
    parts = text.split("`")
    if len(parts) % 2 == 0:
        refuse(f"an unclosed code span in {text[:60]!r}")
    runs = []
    for i, part in enumerate(parts):
        if i % 2:
            runs.append(("code", part))
            continue
        pieces = part.split("**")
        if len(pieces) % 2 == 0:
            refuse(f"an unclosed bold span in {text[:60]!r}")
        runs += [(BOLDER[role] if j % 2 else role, piece) for j, piece in enumerate(pieces)]
    return [(r, part) for r, part in runs if part]


def wrap(runs, size, width):
    """Lines of runs that fit `width`, broken between words, or inside a word too long for a line."""
    # A column is exactly as wide as its widest cell; without this allowance the
    # rounding of width + padding - padding would break that cell in two.
    width += 0.001
    lines, line, used = [], [], 0.0

    def push():
        nonlocal line, used
        if line:
            role, text = line[-1]
            line[-1] = (role, text.rstrip())
            lines.append(line)
        line, used = [], 0.0

    for role, text in runs:
        for token in re.findall(r"\S+\s*|\s+", text):
            if not token.strip():
                if line:
                    line.append((role, token))
                    used += advance(role, token, size)
                continue
            if line and used + advance(role, token.rstrip(), size) > width:
                if token[0] in CLINGING:
                    # A mark that cannot start a line belongs to the word before
                    # it, so that word goes down to the next line with it.
                    held = []
                    while len(line) > 1 and not line[-1][1].endswith(" "):
                        held.insert(0, line.pop())
                    push()
                    for face, word in held:
                        line.append((face, word))
                        used += advance(face, word, size)
                else:
                    push()
            while advance(role, token.rstrip(), size) > width:
                cut = len(token) - 1
                while cut > 1 and advance(role, token[:cut], size) > width:
                    cut -= 1
                line.append((role, token[:cut]))
                push()
                token = token[cut:]
            line.append((role, token))
            used += advance(role, token, size)
    push()
    return lines or [[]]


def colour(rgb):
    return f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg"


def figure_colour(text, benchmark=False):
    """What a figure is, said in colour: the benchmark, a loss, a gain, or a plain measure.

    Only a figure that states a direction is coloured. A volatility, an index or
    a count is a measure and stays in the ink of the page.
    """
    if benchmark:
        return BENCHMARK
    if text.startswith(("−", "-")):
        return LOSS
    if text.startswith("+"):
        return GREEN
    return INK


def draw(x, y, line, size, ink=INK, tracking=0.0):
    """Drawing operators for a line; the words of one face are drawn as one string, so a reader can find a phrase."""
    merged = []
    for role, text in line:
        if merged and merged[-1][0] == role:
            merged[-1][1] += text
        else:
            merged.append([role, text])
    ops = [colour(ink)]
    for role, text in merged:
        if text:
            # The letter spacing is stated every time. A text object inherits it
            # from the one before, so a tracked line would otherwise widen every
            # line drawn after it on the page.
            ops.append(f"BT /{RESOURCE[role]} {size:.2f} Tf {tracking * size:.3f} Tc "
                       f"{x:.2f} {y:.2f} Td ({escape(encode(text))}) Tj ET")
        x += advance(role, text, size, tracking)
    return ops


def rule(x1, x2, y, weight, ink=INK):
    return (f"{ink[0]:.3f} {ink[1]:.3f} {ink[2]:.3f} G {weight:.2f} w "
            f"{x1:.2f} {y:.2f} m {x2:.2f} {y:.2f} l S")


def box(x1, y1, x2, y2, weight, ink=RULE_STRONG):
    return (f"{ink[0]:.3f} {ink[1]:.3f} {ink[2]:.3f} G {weight:.2f} w "
            f"{x1:.2f} {y1:.2f} {x2 - x1:.2f} {y2 - y1:.2f} re S")


# --- layout -----------------------------------------------------------------

class Pages:

    def __init__(self):
        self.pages = []
        self.new()

    def new(self):
        self.ops = []
        self.pages.append(self.ops)
        self.links = []                           # [(x1, y1, x2, y2, uri)] on this page
        self.all_links = getattr(self, "all_links", []) + [self.links]
        self.y = PAGE_H - TOP

    def at_top(self):
        return self.y >= PAGE_H - TOP

    def room(self, height):
        if self.y - height < BOTTOM and not self.at_top():
            self.new()


def block(pages, text, kind, role="text", ink=INK, indent=0.0, bullet=None, keep=0.0, width=None):
    size, leading, before, after = STYLE[kind]
    lines = wrap(spans(text, role), size, (width or WIDTH) - indent)
    if not pages.at_top():
        pages.y -= before
    pages.room(leading + keep)
    for i, line in enumerate(lines):
        pages.room(leading)
        pages.y -= leading
        if bullet and i == 0:
            pages.ops += draw(LEFT, pages.y, [(role, bullet)], size, FAINT)
        pages.ops += draw(LEFT + indent, pages.y, line, size, ink)
    pages.y -= after


def wordmark(x, y, size):
    """The name, set in the house typeface. Only the full stop carries the brand colour."""
    ops = draw(x, y, [("label-bold", "reout")], size, INK, WORDMARK_TRACKING)
    stop = x + advance("label-bold", "reout", size, WORDMARK_TRACKING)
    ops += draw(stop, y, [("label-bold", ".")], size, GREEN, WORDMARK_TRACKING)
    return ops, stop + advance("label-bold", ".", size, WORDMARK_TRACKING)


def terms_table(pages, terms):
    """The programme's terms, as a datasheet states them: label, value, hairline."""
    size = 8.0
    height = len(terms) * 15.0
    pages.room(height + 8.0)
    top = pages.y
    for j, (label, value) in enumerate(terms):
        y = top - (j + 1) * 15.0 + 4.6
        pages.ops += draw(LEFT + 8.0, y, [("label", label)], size, MUTED)
        runs = spans(value, "figure")
        width = sum(advance(role, text, size) for role, text in runs)
        pages.ops += draw(LEFT + WIDTH - 8.0 - width, y, runs, size, INK)
        # An address the record keeps, written as a code span, is a link where it is drawn.
        x = LEFT + WIDTH - 8.0 - width
        for role, text in runs:
            step = advance(role, text, size)
            if role == "code" and text in LINKS:
                pages.links.append((x, y - 2.2, x + step, y + 7.4, LINKS[text]))
            x += step
        if j:
            pages.ops.append(rule(LEFT, LEFT + WIDTH, top - j * 15.0, 0.4, RULE))
    pages.ops.append(box(LEFT, top - height, LEFT + WIDTH, top, 0.5))
    pages.y = top - height


def masthead(pages, label, title, straplines, terms):
    """The head of the sheet: the name, the report it is, a heavy rule, the terms."""
    size = 11.0
    ops, _ = wordmark(LEFT, pages.y - size, size)
    pages.ops += ops
    if label:
        right = LEFT + WIDTH - advance("figure", label, 7.4, 0.06)
        # The label says what the report is. A label is not the brand's mark.
        pages.ops += draw(right, pages.y - size + 0.8, [("figure", label)], 7.4, FAINT, 0.06)
    pages.y -= size + 7.0
    # The brand appears as a rule, not as a field of colour.
    pages.ops.append(rule(LEFT, LEFT + WIDTH, pages.y, 2.4, INK))
    pages.y -= 20.0
    block(pages, title, "title", role="label-bold")
    pages.y -= 4.0
    for i, line in enumerate(straplines):
        block(pages, line, "p", ink=MUTED if i == 0 else INK, width=MEASURE)
    if terms:
        pages.y -= 2.0
        terms_table(pages, terms)
        pages.y -= 14.0


def fit(natural, width):
    """Column widths: each column its natural width, the widest shrunk equally when they do not fit."""
    if sum(natural) <= width:
        return list(natural)
    widths, remaining = list(natural), width
    left = sorted(range(len(natural)), key=lambda j: natural[j])
    while left:
        share = remaining / len(left)
        if natural[left[0]] <= share:
            remaining -= natural[left[0]]
            left.pop(0)
        else:
            for j in left:
                widths[j] = share
            break
    return widths


def runs_width(runs, size):
    return sum(advance(role, text, size) for role, text in runs)


def cell_runs(cell, role):
    """A cell that opens with a figure: the figure as a figure, whatever follows it in `role`.

    A measure is often stated as a figure and a qualification — a return "for the
    period", a ratio "from 214 daily returns". The figure is still a figure.
    """
    opening = re.match(r"[+\-−]?\d[\d,.]*%?(?=$|[ ,])|—(?=$|[ ,])", cell)
    if role == "figure" or not opening:
        return spans(cell, role)
    return [("figure", opening.group(0))] + spans(cell[opening.end():], role)


def table(pages, source_lines):
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in source_lines]
    if len(rows) < 2 or not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", source_lines[1].strip()):
        refuse("a table without its header separator")
    header, body = rows[0], rows[2:]
    if any(len(row) != len(header) for row in body):
        refuse("a table whose rows differ in their number of cells")
    size, leading, before, after = STYLE["table"]
    n = len(header)
    # A table whose first heading is empty states a measure and its values; one
    # that names its first column is a series. The first is set as the site sets
    # a key and its value, the second as it sets a table.
    measures = not header[0]
    numeric = [j > 0 and bool(body) and all(NUMERIC.fullmatch(r[j]) for r in body if r[j]) for j in range(n)]
    # The benchmark is a series of its own, and keeps its colour wherever it is
    # stated: a column of its own, or a row of a table of measures.
    benchmark = ["benchmark" in cell.lower() for cell in header]

    def role_of(j, head=False):
        return "label" if head or not numeric[j] else "figure"

    natural = [max(runs_width(cell_runs(row[j], role_of(j, k == 0)), size)
                   for k, row in enumerate([header] + body)) + 2 * PAD for j in range(n)]
    widths = fit(natural, WIDTH)
    right = LEFT + sum(widths)

    def layout(row, head=False):
        cells = [wrap(cell_runs(cell, role_of(j, head)), size, widths[j] - 2 * PAD)
                 for j, cell in enumerate(row)]
        return cells, max(len(c) for c in cells) * leading + 5.0

    def draw_row(cells, height, head=False, benchmark_row=False):
        top, x = pages.y, LEFT
        for j, lines in enumerate(cells):
            for k, line in enumerate(lines):
                y = top - 3.0 - (k + 1) * leading + 3.0
                figure = bool(line) and line[0][0] == "figure"
                ink = FAINT if head else (MUTED if measures and j == 0 and not figure else INK)
                if not head and figure:
                    ink = figure_colour(line[0][1], benchmark[j] or benchmark_row)
                if numeric[j]:
                    w = sum(advance(r, t, size) for r, t in line)
                    pages.ops += draw(x + widths[j] - PAD - w, y, line, size, ink)
                else:
                    pages.ops += draw(x + PAD, y, line, size, ink)
            x += widths[j]
        pages.y = top - height

    head_cells, head_height = layout(header, head=True)

    def draw_header():
        draw_row(head_cells, head_height, head=True)
        pages.ops.append(rule(LEFT, right, pages.y, 0.7, INK))

    if not pages.at_top():
        pages.y -= before
    pages.room(head_height + leading + 8.0)
    draw_header()
    for i, row in enumerate(body):
        cells, height = layout(row)
        if pages.y - height < BOTTOM:
            pages.new()
            draw_header()
        draw_row(cells, height, benchmark_row=measures and "benchmark" in row[0].lower())
        if i < len(body) - 1:
            pages.ops.append(rule(LEFT, right, pages.y, 0.4, RULE))
    pages.y -= after


def advance_of(cell, role, size):
    return sum(advance(r, t, size) for r, t in spans(cell, role))


def footer(pages, source, digest, label=None):
    """The foot of every page: what the report is, its page and the hash of its Markdown."""
    month = re.search(r"\d{4}-\d{2}", source)
    name = label or (f"Monthly report {month.group(0)}" if month else "Monthly report")
    count = len(pages.pages)
    for number, ops in enumerate(pages.pages, start=1):
        base = BOTTOM - 32.0
        ops.append(rule(LEFT, PAGE_W - RIGHT, base + 16.0, 0.4, RULE_STRONG))
        marks, x = wordmark(LEFT, base + 5.0, 7.2)
        ops += marks
        ops += draw(x + 5.0, base + 5.0, [("label", name)], 7.2, MUTED)
        page = f"page {number} of {count}"
        ops += draw(PAGE_W - RIGHT - advance("figure", page, 7.0), base + 5.0,
                    [("figure", page)], 7.0, FAINT)
        ops += draw(LEFT, base - 5.0, [("label", f"Rendered from {source}, SHA-256 ")], 6.4, FAINT)
        ops += draw(LEFT + advance("label", f"Rendered from {source}, SHA-256 ", 6.4), base - 5.0,
                    [("code", digest)], 6.4, FAINT)


# --- the file ---------------------------------------------------------------

def subset_tag(face):
    """The six letters a subset of a face is named by, from the bytes themselves."""
    digest = metrics.FACES[face]["sha256"]
    return "".join(chr(ord("A") + int(digest[i * 2:i * 2 + 2], 16) % 26) for i in range(6))


def font_objects(first):
    """The faces, each as a font, a descriptor and the file itself."""
    objects = []
    for i, face in enumerate(EMBEDDED):
        m = metrics.FACES[face]
        with open(os.path.join(FOLDER, face + ".ttf"), "rb") as f:
            data = f.read()
        name = f"{subset_tag(face)}+{face.replace('-', '')}"
        font, descriptor, file = first + 3 * i, first + 3 * i + 1, first + 3 * i + 2
        objects.append(
            f"<< /Type /Font /Subtype /TrueType /BaseFont /{name} "
            f"/FirstChar {metrics.FIRST_CODE} /LastChar 255 "
            f"/Widths [{' '.join(str(w) for w in m['widths'])}] "
            f"/FontDescriptor {descriptor} 0 R "
            f"/Encoding << /Type /Encoding /BaseEncoding /WinAnsiEncoding "
            f"/Differences [{metrics.MINUS_CODE} /minus] >> >>")
        objects.append(
            f"<< /Type /FontDescriptor /FontName /{name} /Flags {m['flags']} "
            f"/FontBBox [{' '.join(str(v) for v in m['bbox'])}] /ItalicAngle {m['italic_angle']} "
            f"/Ascent {m['ascent']} /Descent {m['descent']} /CapHeight {m['cap_height']} "
            f"/StemV {m['stem_v']} /FontFile2 {file} 0 R >>")
        objects.append(b"<< /Length %d /Length1 %d >>\nstream\n" % (len(data), len(data))
                       + data + b"\nendstream")
    return objects


def assemble(pages, title, links=None):
    links = links or [[] for _ in pages]
    count = len(pages)
    first_font = 4
    first_page = first_font + 3 * len(EMBEDDED)
    # The links follow the pages, each an annotation of the page it sits on.
    first_link, numbers = first_page + 2 * count, []
    for here in links:
        numbers.append([first_link + sum(len(h) for h in numbers) + k for k in range(len(here))])
    resources = " ".join(f"/F{i + 1} {first_font + 3 * i} 0 R" for i in range(len(EMBEDDED)))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R /Lang (en) >>",
        "<< /Type /Pages /Kids [" + " ".join(f"{first_page + 2 * i} 0 R" for i in range(count))
        + f"] /Count {count} >>",
        f"<< /Title ({escape(encode(title))}) /Producer (tools/report_pdf.py) >>",
    ]
    objects += font_objects(first_font)
    for i, ops in enumerate(pages):
        annots = f" /Annots [{' '.join(f'{n} 0 R' for n in numbers[i])}]" if numbers[i] else ""
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                       f"/Resources << /Font << {resources} >> >> /Contents {first_page + 2 * i + 1} 0 R{annots} >>")
        stream = "\n".join(ops).encode("ascii")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    for here in links:
        for x1, y1, x2, y2, uri in here:
            objects.append(f"<< /Type /Annot /Subtype /Link /Rect [{x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f}] "
                           f"/Border [0 0 0] /A << /S /URI /URI ({escape(encode(uri))}) >> >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + (body if isinstance(body, bytes) else body.encode("ascii")) + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info 3 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start)
    return bytes(out)


def render(markdown, source, digest, label=None):
    """The PDF of `markdown`, published as `source` with the SHA-256 `digest`.

    `label` names the report in the head and in the foot of every page.
    """
    pages = Pages()
    lines = markdown.split("\n")
    title, straplines, terms, colophon = None, [], [], False
    i = 0

    # The head: the title, what it says of itself, and the terms it states.
    if lines and lines[0].startswith("# "):
        title = lines[0][2:]
        i = 1
        while i < len(lines) and not re.match(r"#{2,} |\||---", lines[i]):
            line = lines[i]
            if line.strip():
                if line.startswith("- "):
                    terms.append(line[2:])
                else:
                    straplines.append(line)
            i += 1
        if all(": " in t for t in terms):
            terms = [tuple(t.split(": ", 1)) for t in terms]
        else:
            straplines += [f"- {t}" for t in terms]
            terms = []
        masthead(pages, label, title, straplines, terms)

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            end = i
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            table(pages, lines[i:end])
            i = end
            continue
        if line.startswith("# "):
            title = title or line[2:]
            block(pages, line[2:], "title", role="label-bold")
        elif line.startswith("## "):
            head = line[3:]
            size = STYLE["h2"][0]
            pages.y -= STYLE["h2"][2]
            pages.room(STYLE["h2"][1] + 48.0)
            pages.y -= STYLE["h2"][1]
            # The section number is the brand's mark on the page, as the full
            # stop of the name is.
            numbered = re.match(r"\d+\.\s+", head)
            start = LEFT
            if numbered:
                pages.ops += draw(start, pages.y, [("label-bold", numbered.group(0))], size, GREEN)
                start += advance("label-bold", numbered.group(0), size)
            pages.ops += draw(start, pages.y, spans(head[numbered.end():] if numbered else head,
                                                   "label-bold"), size)
            # The heading sits on the rule, as a printed table divides a page.
            pages.ops.append(rule(LEFT + advance_of(head, "label-bold", size) + 9.0, LEFT + WIDTH,
                                  pages.y + size * 0.33, 0.6, INK))
            pages.y -= STYLE["h2"][3]
        elif line.startswith("### "):
            block(pages, line[4:], "h3", role="label-bold", keep=36.0)
        elif line.startswith("- "):
            block(pages, line[2:], "li", indent=13.0, bullet="—", width=MEASURE)
        elif line.strip() == "---":
            pages.room(14.0)
            pages.y -= 8.0
            pages.ops.append(rule(LEFT, PAGE_W - RIGHT, pages.y, 0.5, RULE_STRONG))
            pages.y -= 11.0
            colophon = True
        elif re.match(r"#|\* |\+ |> |<|```|\d+\. ", line):
            refuse(f"Markdown the report does not write: {line[:40]!r}")
        elif colophon:
            block(pages, line, "note", role="label", ink=FAINT, width=min(MEASURE + 60.0, WIDTH))
        else:
            block(pages, line, "p", width=MEASURE)
        i += 1
    footer(pages, source, digest, label)
    return assemble(pages.pages, title or source, pages.all_links)
