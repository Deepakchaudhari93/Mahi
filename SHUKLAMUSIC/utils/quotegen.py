# -----------------------------------------------
# Quote sticker renderer (Mahi X Music)
#
# - User ka POORA naam, usi stylish unicode font me (ᴹᴿ ᴾᴬᴺᴰᴬ, 𝐌𝐑, ＭＲ ...)
# - Naam ke andar ke emoji + premium emoji status
# - Admin / Owner / Custom title (jaise "PANDU") naam ke saamne
# - Message ke andar normal emoji + premium (custom) emoji
# - Hindi / English / Arabic sab (font fallback chain se)
#
# Ye file Telegram se kuch import nahi karti, sirf Pillow use karti hai.
# -----------------------------------------------
import os
import unicodedata
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, features

FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "quotefonts"
)

try:
    LAYOUT = (
        ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    )
except AttributeError:  # purana Pillow
    LAYOUT = ImageFont.LAYOUT_RAQM if features.check("raqm") else ImageFont.LAYOUT_BASIC

try:
    LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    LANCZOS = Image.LANCZOS

# Pehla font jisme glyph mile wahi use hota hai
_TAIL = ["DejaVuMathTeXGyre.ttf", "FreeSans.ttf", "FreeSerif.ttf", "unifont.otf"]
CHAINS = {
    "r": ["DejaVuSans.ttf"] + _TAIL,
    "b": ["DejaVuSans-Bold.ttf", "DejaVuMathTeXGyre.ttf", "FreeSansBold.ttf", "FreeSerif.ttf", "unifont.otf"],
    "i": ["DejaVuSans-Oblique.ttf"] + _TAIL,
    "bi": ["DejaVuSans-BoldOblique.ttf", "DejaVuMathTeXGyre.ttf", "FreeSansBold.ttf", "FreeSerif.ttf", "unifont.otf"],
    "m": ["DejaVuSansMono.ttf", "DejaVuSans.ttf"] + _TAIL,
}

# Telegram ke 7 name colors (red, orange, violet, green, cyan, blue, pink)
COLORS = ["#ff8e86", "#ffa357", "#b18fff", "#85de85", "#4dd6d6", "#7ab5ff", "#ff8fc8"]
LINK_COL = "#6ab7ff"  # /command, @username, #hashtag, link
CODE_COL = "#e8d9ff"

# text styles (entities se)
F_B, F_I, F_U, F_S, F_M, F_L = 1, 2, 4, 8, 16, 32
ENT_FLAGS = {
    "bold": F_B, "italic": F_I, "underline": F_U, "strikethrough": F_S,
    "code": F_M, "pre": F_M,
    "mention": F_L, "text_mention": F_L, "hashtag": F_L, "cashtag": F_L,
    "bot_command": F_L, "url": F_L, "text_link": F_L, "email": F_L, "phone_number": F_L,
}

# ---- layout (logical px, render time par S se multiply hota hai) ----
S = 2  # supersampling, final image 512 wide
W = 512
PAD = 10
AV = 60
GAP = 10
BPX = 16  # bubble padding left/right
BPT = 10
BPB = 12
NAME_SZ, TEXT_SZ, TITLE_SZ, REPLY_SZ = 26, 30, 18, 22

BUBBLE_BG = "#231a38"
TITLE_COL = "#a79fc0"
REPLY_COL = "#b8b0d0"

ZWJ = "\u200d"
ZWNJ = "\u200c"
VS16 = "\ufe0f"
KEYCAP = "\u20e3"

# Default emoji-presentation wale BMP symbols
_EMOJI_PRES = set(
    [0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3, 0x25FD, 0x25FE]
    + [0x2614, 0x2615, 0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE]
    + [0x26C4, 0x26C5, 0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA]
    + [0x26FD, 0x2705, 0x270A, 0x270B, 0x2728, 0x274C, 0x274E, 0x2753, 0x2754]
    + [0x2755, 0x2757, 0x2795, 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B1B, 0x2B1C]
    + [0x2B50, 0x2B55]
    + list(range(0x2648, 0x2654))
)


# ===================================================================
# Fonts
# ===================================================================
_font_cache = {}
_sup_cache = {}
_notdef = {}
_pick_cache = {}


def _font(idx, bold, size):  # "bold" ab variant string hai: r / b / i / bi / m
    key = (idx, bold, size)
    if key not in _font_cache:
        path = os.path.join(FONT_DIR, CHAINS[bold][idx])
        _font_cache[key] = ImageFont.truetype(path, size, layout_engine=LAYOUT)
    return _font_cache[key]


def _glyph(font, ch):
    im = Image.new("L", (100, 100), 0)
    ImageDraw.Draw(im).text((10, 10), ch, font=font, fill=255)
    return im


def _supports(idx, bold, ch):
    key = (idx, bold, ch)
    if key in _sup_cache:
        return _sup_cache[key]
    # unifont khali / unassigned codepoints par hex wale "tofu box" banata hai -> reject
    if CHAINS[bold][idx] == "unifont.otf" and unicodedata.category(ch) in ("Cn", "Co", "Cs", "Cc", "Cf"):
        _sup_cache[key] = False
        return False
    f = _font(idx, bold, 40)
    nk = (idx, bold)
    if nk not in _notdef:
        _notdef[nk] = _glyph(f, "\U0010ffff").tobytes()
    try:
        im = _glyph(f, ch)
        ok = im.getbbox() is not None and im.tobytes() != _notdef[nk]
    except Exception:
        ok = False
    _sup_cache[key] = ok
    return ok


def _pick(ch, bold):
    key = (ch, bold)
    if key not in _pick_cache:
        r = None
        for i in range(len(CHAINS[bold])):
            if _supports(i, bold, ch):
                r = i
                break
        _pick_cache[key] = r
    return _pick_cache[key]


# ===================================================================
# Emoji
# ===================================================================
_emoji_font_obj = None
_emoji_cache = {}


def _emoji_font():
    global _emoji_font_obj
    if _emoji_font_obj is None:
        _emoji_font_obj = ImageFont.truetype(
            os.path.join(FONT_DIR, "NotoColorEmoji.ttf"), 109, layout_engine=LAYOUT
        )
    return _emoji_font_obj


def _emoji_img(cluster):
    if cluster in _emoji_cache:
        return _emoji_cache[cluster]
    res = None
    try:
        im = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), cluster, font=_emoji_font(), embedded_color=True)
        if im.getbbox():
            res = im
    except Exception:
        res = None
    _emoji_cache[cluster] = res
    return res


def _is_skin(c):
    return 0x1F3FB <= ord(c) <= 0x1F3FF


def _is_tag(c):
    return 0xE0020 <= ord(c) <= 0xE007F


def _is_emoji_base(text, i):
    c = text[i]
    o = ord(c)
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if 0x1F000 <= o <= 0x1FAFF:
        return True
    if o in _EMOJI_PRES:
        return True
    if nxt == VS16 and (o >= 0x2000 or o in (0xA9, 0xAE)):
        return True
    if c in "#*0123456789" and nxt in (VS16, KEYCAP):
        return True
    return False


def _emoji_end(text, i):
    """Agar i par emoji shuru hota hai to uska end index, warna i."""
    if not _is_emoji_base(text, i):
        return i
    n = len(text)
    j = i + 1
    if 0x1F1E6 <= ord(text[i]) <= 0x1F1FF:  # flag = 2 regional indicators
        if j < n and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
            j += 1
    while j < n:
        c = text[j]
        if c in (VS16, KEYCAP) or _is_skin(c) or _is_tag(c):
            j += 1
        elif c == ZWJ and j + 1 < n and _is_emoji_base(text, j + 1):
            j += 2
        else:
            break
    return j


def _u16(c):
    return 2 if ord(c) > 0xFFFF else 1


def _flag_array(text, entities):
    total = sum(_u16(c) for c in text)
    arr = [0] * (total + 2)
    for e in entities or []:
        f = ENT_FLAGS.get(e.get("type"), 0)
        if not f:
            continue
        for p in range(e["offset"], min(total, e["offset"] + e["length"])):
            arr[p] |= f
    return arr


def tokenize(text, custom=None, entities=None):
    """text -> tokens. custom = [(utf16_offset, utf16_length, custom_emoji_id)]"""
    ranges = {o: (ln, cid) for o, ln, cid in (custom or [])}
    farr = _flag_array(text, entities) if entities else None
    toks, pos, i, n = [], 0, 0, len(text)
    while i < n:
        if pos in ranges:
            ln, cid = ranges[pos]
            j, u = i, 0
            while j < n and u < ln:
                u += _u16(text[j])
                j += 1
            toks.append(("custom", cid, text[i:j]))
            pos += u
            i = j
            continue
        ch = text[i]
        if ch == "\n":
            toks.append(("nl",))
            pos += 1
            i += 1
            continue
        e = _emoji_end(text, i)
        if e > i:
            cl = text[i:e]
            toks.append(("emoji", cl))
            pos += sum(_u16(c) for c in cl)
            i = e
            continue
        toks.append(("ch", ch, farr[pos] if farr else 0))
        pos += _u16(ch)
        i += 1
    return toks


# ===================================================================
# Items / wrapping
# ===================================================================
def _var(fl, base):
    if fl & F_M:
        return "m"
    bold = base == "b" or fl & F_B
    ital = fl & F_I
    return "bi" if (bold and ital) else "b" if bold else "i" if ital else "r"


def _build_runs(toks, base):
    """tokens -> (kind, ...) tuples; same font+style ke chars ek run me (shaping ke liye)."""
    items, cur = [], None

    def flush():
        nonlocal cur
        if cur:
            items.append(("run", cur[1], cur[0], cur[2]))
            cur = None

    for t in toks:
        k = t[0]
        if k == "nl":
            flush()
            items.append(("nl",))
        elif k == "emoji":
            flush()
            items.append(("emoji", t[1]))
        elif k == "custom":
            flush()
            items.append(("custom", t[1], t[2]))
        else:
            ch = t[1]
            fl = t[2] if len(t) > 2 else 0
            if ch in " \t\u00a0\u3000":
                flush()
                items.append(("sp", fl))
                continue
            if ch in (ZWJ, ZWNJ):
                if cur:
                    cur[1] += ch
                continue
            cat = unicodedata.category(ch)
            if cat in ("Mn", "Mc", "Me"):
                # matra / combining mark: apne base ke saath, warna ring ya drop
                if cur and _supports(cur[0], _var(cur[2], base), ch):
                    cur[1] += ch
                elif cat == "Me" and not cur and items and items[-1][0] in ("emoji", "custom"):
                    items.append(("ring", ch))
                elif cat == "Me" and cur is None:
                    pass
                continue
            idx = _pick(ch, _var(fl, base))
            if idx is None:
                continue
            if cur and cur[0] == idx and cur[2] == fl:
                cur[1] += ch
            else:
                flush()
                cur = [idx, ch, fl]
    flush()
    return items


def _measure(items, size, base):
    out = []
    for it in items:
        k = it[0]
        if k == "run":
            f = _font(it[2], _var(it[3], base), size)
            out.append({"k": "run", "t": it[1], "f": f, "w": f.getlength(it[1]), "fl": it[3]})
        elif k == "sp":
            out.append({"k": "sp", "w": _font(0, base, size).getlength(" ")})
        elif k == "nl":
            out.append({"k": "nl", "w": 0})
        elif k == "ring":
            out.append({"k": "ring", "t": it[1], "w": 0})
        elif k == "emoji":
            out.append({"k": "emoji", "t": it[1], "w": size * 1.2})
        else:
            out.append({"k": "custom", "id": it[1], "t": it[2], "w": size * 1.2})
    return out


def _make(text, size, base, custom=None, entities=None):
    return _measure(_build_runs(tokenize(text, custom, entities), base), size, base)


def _split_run(it, max_w):
    t, parts = it["t"], []
    while t:
        n = len(t)
        while n > 1 and it["f"].getlength(t[:n]) > max_w:
            n -= 1
        parts.append(dict(it, t=t[:n], w=it["f"].getlength(t[:n])))
        t = t[n:]
    return parts


def _wrap(items, max_w):
    lines, w = [[]], 0
    for it in items:
        k = it["k"]
        if k == "nl":
            lines.append([])
            w = 0
            continue
        if k == "sp":
            if lines[-1]:
                lines[-1].append(it)
                w += it["w"]
            continue
        pieces = _split_run(it, max_w) if (k == "run" and it["w"] > max_w) else [it]
        for p in pieces:
            if lines[-1] and w + p["w"] > max_w + 0.01:
                while lines[-1] and lines[-1][-1]["k"] == "sp":
                    lines[-1].pop()
                lines.append([])
                w = 0
            lines[-1].append(p)
            w += p["w"]
    for ln in lines:
        while ln and ln[-1]["k"] == "sp":
            ln.pop()
    return lines


def _lw(line):
    return sum(i["w"] for i in line)


def _clamp(lines, n, max_w, size, bold):
    if len(lines) <= n:
        return lines
    lines = lines[:n]
    last = lines[-1]
    f = _font(0, bold, size)
    ew = f.getlength("…")
    while last and _lw(last) + ew > max_w:
        last.pop()
    last.append({"k": "run", "t": "…", "f": f, "w": ew})
    return lines


# ===================================================================
# Drawing
# ===================================================================
def _draw_line(canvas, d, x, base, line, size, fill, custom_imgs):
    last = None
    for it in line:
        k = it["k"]
        if k == "run":
            fl = it.get("fl", 0)
            col = LINK_COL if fl & F_L else (CODE_COL if fl & F_M else fill)
            d.text((x, base), it["t"], font=it["f"], fill=col, anchor="ls")
            lw = max(1, int(size * 0.06))
            if fl & F_U:
                d.line((x, base + size * 0.12, x + it["w"], base + size * 0.12), fill=col, width=lw)
            if fl & F_S:
                d.line((x, base - size * 0.3, x + it["w"], base - size * 0.3), fill=col, width=lw)
        elif k in ("emoji", "custom"):
            img = custom_imgs.get(it.get("id")) if k == "custom" else None
            if img is None and it.get("t"):
                img = _emoji_img(it["t"])
            if img is not None:
                px = int(size * 1.12)
                im = img.resize((px, max(1, int(px * img.height / img.width))), LANCZOS)
                ix, iy = int(x), int(base - size * 0.92)
                canvas.paste(im, (ix, iy), im)
                last = (ix, iy, px, im.height)
        elif k == "ring" and last:
            # emoji ke upar enclosing mark (⃝ ⃞ ⃟ ⃠ ⃤) jaise Telegram me dikhta hai
            ix, iy, pw, ph = last
            pad = size * 0.12
            box = (ix - pad, iy - pad, ix + pw + pad, iy + ph + pad)
            lw = max(1, int(size * 0.07))
            c = it["t"]
            if c in ("\u20de", "\u20e2"):
                d.rectangle(box, outline=fill, width=lw)
            elif c == "\u20df":
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                d.polygon([(cx, box[1]), (box[2], cy), (cx, box[3]), (box[0], cy)], outline=fill, width=lw)
            elif c == "\u20e4":
                d.polygon([((box[0] + box[2]) / 2, box[1]), (box[2], box[3]), (box[0], box[3])], outline=fill, width=lw)
            else:
                d.ellipse(box, outline=fill, width=lw)
                if c == "\u20e0":
                    d.line((box[0], box[3], box[2], box[1]), fill=fill, width=lw)
        x += it["w"]


def _avatar(b, size, col):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    av = b.get("avatar")
    if av is not None:
        w, h = av.size
        m = min(w, h)
        av = av.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m))
        return av.resize((size, size), LANCZOS).convert("RGBA"), mask
    base = Image.new("RGBA", (size, size), col)
    letter = "?"
    for t in tokenize(b.get("name") or ""):
        if t[0] == "ch" and unicodedata.category(t[1])[0] in ("L", "N"):
            letter = t[1].upper()
            break
    idx = _pick(letter, "b")
    if idx is not None:
        ImageDraw.Draw(base).text(
            (size // 2, size // 2),
            letter,
            font=_font(idx, "b", int(size * 0.5)),
            fill="white",
            anchor="mm",
        )
    return base, mask


def _prep(b):
    ns, ts, cs, rs = (v * S for v in (NAME_SZ, TEXT_SZ, TITLE_SZ, REPLY_SZ))
    max_inner = (W - PAD - AV - GAP - PAD - 2 * BPX) * S

    title_items = _make(b["title"][:24], cs, "r") if b.get("title") else []
    title_w = _lw(title_items)
    title_gap = 14 * S if title_items else 0

    name_items = _make(b.get("name") or "", ns, "b")
    if b.get("status_id"):
        name_items += [
            {"k": "sp", "w": _font(0, "b", ns).getlength(" ")},
            {"k": "custom", "id": b["status_id"], "t": "", "w": ns * 1.2},
        ]
    name_max = max_inner - title_w - title_gap
    name_lines = _clamp(_wrap(name_items, name_max), 2, name_max, ns, "b")
    if not name_lines or not name_lines[0]:
        name_lines = [_make("User", ns, "b")]

    text_items = _make(b.get("text") or "", ts, "r", b.get("custom"), b.get("entities"))
    text_lines = _wrap(text_items, max_inner)
    if not any(text_lines):
        text_lines = [_make("…", ts, "r")]

    reply_line = None
    if b.get("reply"):
        r = b["reply"]
        ritems = _make(f"{r.get('name') or ''}: {r.get('text') or ''}".replace("\n", " "), rs, "r")
        reply_line = _clamp(_wrap(ritems, max_inner - 12 * S), 1, max_inner - 12 * S, rs, "r")[0]

    widths = [_lw(name_lines[0]) + title_gap + title_w]
    widths += [_lw(l) for l in name_lines[1:]]
    widths += [_lw(l) for l in text_lines]
    if reply_line:
        widths.append(_lw(reply_line) + 12 * S)
    iw = int(max(max(widths), 50 * S))

    nlh, tlh, rlh = int(ns * 1.3), int(ts * 1.32), int(rs * 1.35)
    h = BPT * S + len(name_lines) * nlh + len(text_lines) * tlh + BPB * S
    if reply_line:
        h += rlh + 6 * S
    return dict(
        b=b, iw=iw, h=int(h), name_lines=name_lines, text_lines=text_lines,
        title_items=title_items, title_w=title_w, reply_line=reply_line,
        nlh=nlh, tlh=tlh, rlh=rlh, ns=ns, ts=ts, cs=cs, rs=rs,
    )


def render_quote(blocks, custom_imgs=None):
    """blocks -> WEBP bytes (sticker ready).

    block = {id, name, title, text, custom:[(off,len,id)], status_id,
             avatar:PIL.Image|None, reply:{name,text}|None}
    """
    custom_imgs = custom_imgs or {}
    pre = [_prep(b) for b in blocks]
    gap = 8 * S
    total_h = PAD * 2 * S + sum(p["h"] for p in pre) + gap * (len(pre) - 1)
    canvas = Image.new("RGBA", (W * S, int(total_h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    y = PAD * S
    bx = (PAD + AV + GAP) * S
    for p in pre:
        b = p["b"]
        col = b.get("color") or COLORS[abs(int(b.get("id") or 0)) % len(COLORS)]
        bw = p["iw"] + 2 * BPX * S
        d.rounded_rectangle((bx, y, bx + bw, y + p["h"]), radius=20 * S, fill=BUBBLE_BG)

        # avatar (bubble ke neeche align)
        av, mask = _avatar(b, AV * S, col)
        ay = y + max(0, p["h"] - AV * S)
        canvas.paste(av, (PAD * S, int(ay)), mask)

        tx = bx + BPX * S
        ty = y + BPT * S
        # name lines
        for i, ln in enumerate(p["name_lines"]):
            base = ty + int(p["ns"] * 1.0)
            _draw_line(canvas, d, tx, base, ln, p["ns"], col, custom_imgs)
            if i == 0 and p["title_items"]:
                _draw_line(
                    canvas, d, tx + p["iw"] - p["title_w"], base - int(p["ns"] * 0.04),
                    p["title_items"], p["cs"], TITLE_COL, custom_imgs,
                )
            ty += p["nlh"]
        # reply
        if p["reply_line"]:
            d.rounded_rectangle((tx, ty, tx + 3 * S, ty + p["rlh"] - 2 * S), radius=S, fill=col)
            _draw_line(
                canvas, d, tx + 12 * S, ty + int(p["rs"] * 0.95), p["reply_line"],
                p["rs"], REPLY_COL, custom_imgs,
            )
            ty += p["rlh"] + 6 * S
        # text
        for ln in p["text_lines"]:
            _draw_line(canvas, d, tx, ty + int(p["ts"] * 1.0), ln, p["ts"], "white", custom_imgs)
            ty += p["tlh"]
        y += p["h"] + gap

    img = canvas.resize((W, max(1, canvas.height // S)), LANCZOS)
    img.thumbnail((512, 512), LANCZOS)

    for kw in ({"lossless": True}, {"quality": 90}, {"quality": 70}):
        out = BytesIO()
        img.save(out, "WEBP", **kw)
        if out.tell() < 500 * 1024:
            break
    return out.getvalue()
