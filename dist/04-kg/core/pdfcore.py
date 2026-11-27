"""Pure-stdlib PDF object reader and layout-aware text extractor.

No third-party dependencies. Handles classic xref tables, xref streams,
object streams, Flate/ASCIIHex/ASCII85/RunLength/LZW filters, and the
content-stream text operators needed to recover positioned glyphs.
"""
from __future__ import annotations

import math
import re
import zlib

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMS = b"()<>[]{}/%"


def _collapse_refs(items):
    """Turn the tokens [num, gen, ('kw','R')] into a Ref."""
    out = []
    i = 0
    n = len(items)
    while i < n:
        it = items[i]
        if (isinstance(it, int) and not isinstance(it, bool) and i + 2 < n
                and isinstance(items[i + 1], int) and not isinstance(items[i + 1], bool)
                and isinstance(items[i + 2], tuple) and items[i + 2] == ("kw", "R")):
            out.append(Ref(it, items[i + 1]))
            i += 3
            continue
        out.append(it)
        i += 1
    return out


class PdfError(Exception):
    pass


class Ref:
    __slots__ = ("num", "gen")

    def __init__(self, num, gen=0):
        self.num = num
        self.gen = gen

    def __repr__(self):
        return "Ref(%d,%d)" % (self.num, self.gen)

    def __eq__(self, other):
        return isinstance(other, Ref) and other.num == self.num

    def __hash__(self):
        return hash(("ref", self.num))


class Name(str):
    """Distinct from a plain string so dict lookups stay unambiguous."""
    __slots__ = ()


# ---------------------------------------------------------------- lexer

class Lexer:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos
        self.n = len(data)

    def skip_ws(self):
        d, n = self.d, self.n
        p = self.p
        while p < n:
            c = d[p]
            if c in WHITESPACE:
                p += 1
            elif c == 0x25:  # '%'
                while p < n and d[p] not in b"\r\n":
                    p += 1
            else:
                break
        self.p = p

    def parse_object(self, depth=0):
        self.skip_ws()
        if self.p >= self.n:
            return None
        d = self.d
        c = d[self.p]
        if c == 0x2F:  # '/'
            self.p += 1
            s = self.p
            while self.p < self.n and d[self.p] not in WHITESPACE and d[self.p] not in DELIMS:
                self.p += 1
            raw = d[s:self.p]
            raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)
            return Name(raw.decode("latin-1"))
        if c == 0x28:  # '('
            return self._literal_string()
        if c == 0x3C:  # '<'
            if self.p + 1 < self.n and d[self.p + 1] == 0x3C:
                self.p += 2
                return self._dict(depth)
            return self._hex_string()
        if c == 0x5B:  # '['
            self.p += 1
            out = []
            while True:
                self.skip_ws()
                if self.p >= self.n:
                    break
                if d[self.p] == 0x5D:
                    self.p += 1
                    break
                out.append(self.parse_object(depth + 1))
            return _collapse_refs(out)
        if c == 0x5D:
            self.p += 1
            return None
        # keyword / number
        s = self.p
        while self.p < self.n and d[self.p] not in WHITESPACE and d[self.p] not in DELIMS:
            self.p += 1
        word = d[s:self.p]
        if not word:
            self.p += 1
            return None
        if re.fullmatch(rb"[+-]?(\d+\.?\d*|\.\d+)", word):
            if b"." in word:
                return float(word)
            return int(word)
        if word == b"true":
            return True
        if word == b"false":
            return False
        if word == b"null":
            return None
        return ("kw", word.decode("latin-1"))

    def _literal_string(self):
        d = self.d
        self.p += 1
        depth = 1
        out = bytearray()
        while self.p < self.n:
            c = d[self.p]
            if c == 0x5C:  # backslash
                self.p += 1
                if self.p >= self.n:
                    break
                e = d[self.p]
                if e in b"nrtbf":
                    out.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}[e])
                    self.p += 1
                elif 0x30 <= e <= 0x37:
                    oct_digits = bytearray()
                    while self.p < self.n and 0x30 <= d[self.p] <= 0x37 and len(oct_digits) < 3:
                        oct_digits.append(d[self.p])
                        self.p += 1
                    out.append(int(oct_digits, 8) & 0xFF)
                elif e in b"\r\n":
                    self.p += 1
                    if e == 0x0D and self.p < self.n and d[self.p] == 0x0A:
                        self.p += 1
                else:
                    out.append(e)
                    self.p += 1
                continue
            if c == 0x28:
                depth += 1
                out.append(c)
                self.p += 1
                continue
            if c == 0x29:
                depth -= 1
                self.p += 1
                if depth == 0:
                    break
                out.append(0x29)
                continue
            out.append(c)
            self.p += 1
        return bytes(out)

    def _hex_string(self):
        d = self.d
        self.p += 1
        s = self.p
        while self.p < self.n and d[self.p] != 0x3E:
            self.p += 1
        raw = re.sub(rb"[^0-9A-Fa-f]", b"", d[s:self.p])
        self.p += 1
        if len(raw) % 2:
            raw += b"0"
        return bytes.fromhex(raw.decode("ascii"))

    def _dict(self, depth):
        out = {}
        while True:
            self.skip_ws()
            if self.p >= self.n:
                break
            if self.d[self.p] == 0x3E and self.p + 1 < self.n and self.d[self.p + 1] == 0x3E:
                self.p += 2
                break
            key = self.parse_object(depth + 1)
            if not isinstance(key, Name):
                continue
            val = self.parse_object(depth + 1)
            # collapse "num gen R"
            if isinstance(val, int):
                save = self.p
                self.skip_ws()
                g = self.parse_object(depth + 1)
                if isinstance(g, int):
                    self.skip_ws()
                    r = self.parse_object(depth + 1)
                    if isinstance(r, tuple) and r[0] == "kw" and r[1] == "R":
                        val = Ref(val, g)
                    else:
                        self.p = save
                else:
                    self.p = save
            out[str(key)] = val
        return out


# ---------------------------------------------------------------- filters

def _inflate(data):
    for wbits in (15, -15, 47):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            continue
    # tolerate trailing garbage / truncated streams
    for wbits in (15, -15, 47):
        try:
            d = zlib.decompressobj(wbits)
            out = d.decompress(data)
            out += d.flush()
            if out:
                return out
        except zlib.error:
            continue
    raise PdfError("flate decode failed")


def _ascii_hex(data):
    raw = re.sub(rb"[^0-9A-Fa-f]", b"", data.split(b">")[0])
    if len(raw) % 2:
        raw += b"0"
    return bytes.fromhex(raw.decode("ascii"))


def _ascii85(data):
    data = re.sub(rb"\s", b"", data)
    if data.startswith(b"<~"):
        data = data[2:]
    end = data.find(b"~>")
    if end >= 0:
        data = data[:end]
    out = bytearray()
    group = []
    for ch in data:
        if ch == 0x7A and not group:  # 'z'
            out += b"\x00\x00\x00\x00"
            continue
        group.append(ch - 33)
        if len(group) == 5:
            v = 0
            for g in group:
                v = v * 85 + g
            out += v.to_bytes(4, "big")
            group = []
    if group:
        pad = 5 - len(group)
        v = 0
        for g in group + [84] * pad:
            v = v * 85 + g
        out += (v & 0xFFFFFFFF).to_bytes(4, "big")[: 4 - pad]
    return bytes(out)


def _runlength(data):
    out = bytearray()
    i = 0
    while i < len(data):
        n = data[i]
        i += 1
        if n == 128:
            break
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        else:
            if i < len(data):
                out += bytes([data[i]]) * (257 - n)
            i += 1
    return bytes(out)


def _lzw(data):
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    bits = 9
    buf = 0
    nbits = 0
    prev = None
    for byte in data:
        buf = (buf << 8) | byte
        nbits += 8
        while nbits >= bits:
            nbits -= bits
            code = (buf >> nbits) & ((1 << bits) - 1)
            if code == 256:
                table = table[:258]
                bits = 9
                prev = None
                continue
            if code == 257:
                return bytes(out)
            if prev is None:
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(prev + entry[:1])
            else:
                entry = prev + prev[:1]
                table.append(entry)
            out += entry
            prev = entry
            if len(table) + 1 >= (1 << bits) and bits < 12:
                bits += 1
    return bytes(out)


def apply_filters(data, filters, parms_list):
    if not isinstance(filters, list):
        filters = [filters] if filters else []
    if not isinstance(parms_list, list):
        parms_list = [parms_list] * len(filters)
    out = data
    for idx, f in enumerate(filters):
        f = str(f)
        parms = parms_list[idx] if idx < len(parms_list) and isinstance(parms_list[idx], dict) else {}
        if f in ("FlateDecode", "Fl"):
            out = _inflate(out)
            predictor = parms.get("Predictor", 1) if parms else 1
            if predictor and predictor >= 10:
                out = _png_unpredict(out, parms.get("Columns", 1), parms.get("Colors", 1), parms.get("BitsPerComponent", 8))
        elif f in ("ASCIIHexDecode", "AHx"):
            out = _ascii_hex(out)
        elif f in ("ASCII85Decode", "A85"):
            out = _ascii85(out)
        elif f in ("RunLengthDecode", "RL"):
            out = _runlength(out)
        elif f in ("LZWDecode", "LZW"):
            out = _lzw(out)
        elif f in ("DCTDecode", "JPXDecode", "CCITTFaxDecode", "JBIG2Decode"):
            raise PdfError("image filter %s" % f)
        else:
            raise PdfError("unsupported filter %s" % f)
    return out


def _png_unpredict(data, columns, colors, bpc):
    bpp = max(1, (colors * bpc + 7) // 8)
    rowlen = (columns * colors * bpc + 7) // 8
    out = bytearray()
    prev = bytearray(rowlen)
    i = 0
    while i + 1 + rowlen <= len(data) + rowlen and i < len(data):
        ft = data[i]
        i += 1
        row = bytearray(data[i:i + rowlen])
        if len(row) < rowlen:
            row += bytes(rowlen - len(row))
        i += rowlen
        for j in range(rowlen):
            a = row[j - bpp] if j >= bpp else 0
            b = prev[j]
            c = prev[j - bpp] if j >= bpp else 0
            if ft == 1:
                row[j] = (row[j] + a) & 0xFF
            elif ft == 2:
                row[j] = (row[j] + b) & 0xFF
            elif ft == 3:
                row[j] = (row[j] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[j] = (row[j] + pr) & 0xFF
        out += row
        prev = row
    return bytes(out)


# ---------------------------------------------------------------- document

class Document:
    def __init__(self, data):
        if not data.startswith(b"%PDF"):
            idx = data.find(b"%PDF")
            if idx < 0:
                raise PdfError("not a PDF")
            data = data[idx:]
        self.raw = data
        self.offsets = {}
        self.trailer = {}
        self._cache = {}
        self._objstm_cache = {}
        self._load_xref()

    # -- xref
    def _load_xref(self):
        try:
            self._load_xref_chain()
        except Exception:
            self.offsets = {}
        if not self.offsets or "Root" not in self.trailer:
            self._reconstruct()

    def _load_xref_chain(self):
        tail = self.raw[-4096:]
        idx = tail.rfind(b"startxref")
        if idx < 0:
            raise PdfError("no startxref")
        m = re.match(rb"startxref\s+(\d+)", tail[idx:])
        if not m:
            raise PdfError("bad startxref")
        off = int(m.group(1))
        seen = set()
        first = True
        while off and off not in seen and off < len(self.raw):
            seen.add(off)
            lex = Lexer(self.raw, off)
            lex.skip_ws()
            if self.raw[off:off + 4] == b"xref":
                trailer = self._read_xref_table(off)
            else:
                trailer = self._read_xref_stream(off)
            if first:
                self.trailer = dict(trailer)
                first = False
            else:
                for k, v in trailer.items():
                    self.trailer.setdefault(k, v)
            prev = trailer.get("Prev")
            off = int(prev) if isinstance(prev, int) else 0

    def _read_xref_table(self, off):
        lex = Lexer(self.raw, off + 4)
        while True:
            lex.skip_ws()
            if self.raw[lex.p:lex.p + 7] == b"trailer":
                lex.p += 7
                trailer = lex.parse_object()
                return trailer if isinstance(trailer, dict) else {}
            start = lex.parse_object()
            count = lex.parse_object()
            if not isinstance(start, int) or not isinstance(count, int):
                raise PdfError("bad xref subsection")
            lex.skip_ws()
            for i in range(count):
                lex.skip_ws()
                line = self.raw[lex.p:lex.p + 20]
                m = re.match(rb"(\d{10})\s+(\d{5})\s+([nf])", line)
                if not m:
                    # tolerate loose spacing
                    parts = line.split()
                    if len(parts) < 3:
                        raise PdfError("bad xref entry")
                    num, gen, kind = int(parts[0]), int(parts[1]), parts[2]
                else:
                    num, gen, kind = int(m.group(1)), int(m.group(2)), m.group(3)
                if kind == b"n" and num:
                    self.offsets[start + i] = ("off", num)
                lex.p += len(m.group(0)) if m else 20
                while lex.p < len(self.raw) and self.raw[lex.p] in b" \r\n":
                    lex.p += 1

    def _read_xref_stream(self, off):
        obj = self._parse_indirect_at(off)
        if not isinstance(obj, dict):
            raise PdfError("bad xref stream")
        data = self._stream_data(obj)
        w = obj.get("W") or [1, 2, 1]
        size = obj.get("Size", 0)
        index = obj.get("Index") or [0, size]
        rec = sum(int(x) for x in w)
        pos = 0
        for i in range(0, len(index) - 1, 2):
            start, count = int(index[i]), int(index[i + 1])
            for j in range(count):
                if pos + rec > len(data):
                    break
                fields = []
                for width in w:
                    width = int(width)
                    if width == 0:
                        fields.append(None)
                    else:
                        fields.append(int.from_bytes(data[pos:pos + width], "big"))
                        pos += width
                ftype = 1 if fields[0] is None else fields[0]
                a = fields[1] or 0
                b = fields[2] or 0
                if ftype == 1 and start + j:
                    self.offsets[start + j] = ("off", a)
                elif ftype == 2 and start + j:
                    self.offsets[start + j] = ("stm", a, b)
        return obj

    def _reconstruct(self):
        self.offsets = {}
        for m in re.finditer(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b", self.raw):
            num = int(m.group(1))
            self.offsets[num] = ("off", m.start())
        trailer = {}
        for m in re.finditer(rb"trailer", self.raw):
            lex = Lexer(self.raw, m.end())
            try:
                t = lex.parse_object()
            except Exception:
                continue
            if isinstance(t, dict):
                trailer.update(t)
        if not trailer.get("Root"):
            for num in sorted(self.offsets):
                try:
                    o = self.get(num)
                except Exception:
                    continue
                if isinstance(o, dict) and str(o.get("Type")) == "Catalog":
                    trailer["Root"] = Ref(num, 0)
                    break
        if not trailer.get("Root"):
            raise PdfError("cannot locate document catalog")
        self.trailer = trailer

    # -- object access
    def _parse_indirect_at(self, off):
        lex = Lexer(self.raw, off)
        num = lex.parse_object()
        gen = lex.parse_object()
        kw = lex.parse_object()
        if not isinstance(kw, tuple) or kw[1] != "obj":
            raise PdfError("expected obj at %d" % off)
        obj = lex.parse_object()
        lex.skip_ws()
        if isinstance(obj, dict) and self.raw[lex.p:lex.p + 6] == b"stream":
            p = lex.p + 6
            if self.raw[p:p + 2] == b"\r\n":
                p += 2
            elif self.raw[p:p + 1] in (b"\n", b"\r"):
                p += 1
            obj["__stream_offset__"] = p
            length = obj.get("Length")
            if isinstance(length, Ref):
                try:
                    length = self.get(length.num)
                except Exception:
                    length = None
            if not isinstance(length, int) or length < 0 or p + length > len(self.raw):
                end = self.raw.find(b"endstream", p)
                length = (end - p) if end > 0 else 0
                while length > 0 and self.raw[p + length - 1] in b"\r\n":
                    length -= 1
            obj["__stream_len__"] = length
        return obj

    def get(self, num):
        if num in self._cache:
            return self._cache[num]
        entry = self.offsets.get(num)
        if entry is None:
            return None
        self._cache[num] = None
        if entry[0] == "off":
            obj = self._parse_indirect_at(entry[1])
        else:
            obj = self._from_objstm(entry[1], entry[2])
        self._cache[num] = obj
        return obj

    def _from_objstm(self, stmnum, idx):
        if stmnum not in self._objstm_cache:
            stm = self.get(stmnum)
            data = self._stream_data(stm)
            first = int(stm.get("First", 0))
            count = int(stm.get("N", 0))
            pairs = []
            lex = Lexer(data, 0)
            for _ in range(count * 2):
                v = lex.parse_object()
                if not isinstance(v, int):
                    break
                pairs.append(v)
            self._objstm_cache[stmnum] = (data, first, pairs)
        data, first, pairs = self._objstm_cache[stmnum]
        if idx * 2 + 1 >= len(pairs):
            return None
        off = first + pairs[idx * 2 + 1]
        lex = Lexer(data, off)
        return lex.parse_object()

    def _stream_data(self, obj):
        if not isinstance(obj, dict) or "__stream_offset__" not in obj:
            return b""
        p = obj["__stream_offset__"]
        n = obj.get("__stream_len__", 0)
        raw = self.raw[p:p + n]
        filters = obj.get("Filter")
        parms = obj.get("DecodeParms", obj.get("DP"))
        return apply_filters(raw, filters, parms)

    def resolve(self, obj, depth=0):
        while isinstance(obj, Ref) and depth < 32:
            obj = self.get(obj.num)
            depth += 1
        return obj

    # -- pages
    def pages(self):
        root = self.resolve(self.trailer.get("Root"))
        if not isinstance(root, dict):
            raise PdfError("bad catalog")
        out = []
        seen = set()

        def walk(node_ref, inherited):
            node = self.resolve(node_ref)
            if not isinstance(node, dict):
                return
            key = node_ref.num if isinstance(node_ref, Ref) else id(node)
            if key in seen:
                return
            seen.add(key)
            inh = dict(inherited)
            for k in ("Resources", "MediaBox", "CropBox", "Rotate"):
                if k in node:
                    inh[k] = node[k]
            typ = str(node.get("Type", ""))
            kids = self.resolve(node.get("Kids"))
            if typ == "Pages" or (isinstance(kids, list) and typ != "Page"):
                for kid in kids or []:
                    walk(kid, inh)
            else:
                page = dict(node)
                for k, v in inh.items():
                    page.setdefault(k, v)
                out.append(page)

        walk(root.get("Pages"), {})
        return out

    def page_content(self, page):
        contents = self.resolve(page.get("Contents"))
        chunks = []
        items = contents if isinstance(contents, list) else [contents]
        for item in items:
            stream = self.resolve(item)
            if isinstance(stream, dict):
                try:
                    chunks.append(self._stream_data(stream))
                except Exception:
                    continue
        return b"\n".join(chunks)


# ---------------------------------------------------------------- fonts

_STANDARD_GLYPHS = {
    "space": " ", "exclam": "!", "quotedbl": '"', "numbersign": "#", "dollar": "$",
    "percent": "%", "ampersand": "&", "quotesingle": "'", "quoteright": "\u2019",
    "quoteleft": "\u2018", "parenleft": "(", "parenright": ")", "asterisk": "*",
    "plus": "+", "comma": ",", "hyphen": "-", "minus": "\u2212", "period": ".",
    "slash": "/", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "colon": ":",
    "semicolon": ";", "less": "<", "equal": "=", "greater": ">", "question": "?",
    "at": "@", "bracketleft": "[", "backslash": "\\", "bracketright": "]",
    "asciicircum": "^", "underscore": "_", "grave": "`", "braceleft": "{", "bar": "|",
    "braceright": "}", "asciitilde": "~", "bullet": "\u2022", "dagger": "\u2020",
    "daggerdbl": "\u2021", "ellipsis": "\u2026", "endash": "\u2013", "emdash": "\u2014",
    "florin": "\u0192", "fraction": "/", "guillemotleft": "\u00ab",
    "guillemotright": "\u00bb", "guilsinglleft": "\u2039", "guilsinglright": "\u203a",
    "quotedblbase": "\u201e", "quotedblleft": "\u201c", "quotedblright": "\u201d",
    "quotesinglbase": "\u201a", "trademark": "\u2122", "fi": "fi", "fl": "fl",
    "ff": "ff", "ffi": "ffi", "ffl": "ffl", "dotlessi": "\u0131", "circumflex": "\u02c6",
    "tilde": "\u02dc", "caron": "\u02c7", "breve": "\u02d8", "dotaccent": "\u02d9",
    "ring": "\u02da", "ogonek": "\u02db", "hungarumlaut": "\u02dd", "perthousand": "\u2030",
    "section": "\u00a7", "paragraph": "\u00b6", "periodcentered": "\u00b7",
    "copyright": "\u00a9", "registered": "\u00ae", "degree": "\u00b0",
    "plusminus": "\u00b1", "multiply": "\u00d7", "divide": "\u00f7",
    "mu": "\u00b5", "germandbls": "\u00df", "ae": "\u00e6", "AE": "\u00c6",
    "oe": "\u0153", "OE": "\u0152", "oslash": "\u00f8", "Oslash": "\u00d8",
    "lslash": "\u0142", "Lslash": "\u0141", "dotlessj": "\u0237",
    "exclamdown": "\u00a1", "questiondown": "\u00bf", "cent": "\u00a2",
    "sterling": "\u00a3", "yen": "\u00a5", "Euro": "\u20ac", "currency": "\u00a4",
    "brokenbar": "\u00a6", "dieresis": "\u00a8", "ordfeminine": "\u00aa",
    "ordmasculine": "\u00ba", "logicalnot": "\u00ac", "macron": "\u00af",
    "acute": "\u00b4", "cedilla": "\u00b8", "onesuperior": "\u00b9",
    "twosuperior": "\u00b2", "threesuperior": "\u00b3", "onequarter": "\u00bc",
    "onehalf": "\u00bd", "threequarters": "\u00be", "Eth": "\u00d0", "eth": "\u00f0",
    "Thorn": "\u00de", "thorn": "\u00fe",
}

_GREEK = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7", "theta": "\u03b8",
    "iota": "\u03b9", "kappa": "\u03ba", "lambda": "\u03bb", "mu": "\u03bc",
    "nu": "\u03bd", "xi": "\u03be", "omicron": "\u03bf", "pi": "\u03c0",
    "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4", "upsilon": "\u03c5",
    "phi": "\u03c6", "chi": "\u03c7", "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3", "Upsilon": "\u03a5",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
}

_ACCENTS = {
    "acute": "\u0301", "grave": "\u0300", "circumflex": "\u0302", "dieresis": "\u0308",
    "tilde": "\u0303", "ring": "\u030a", "cedilla": "\u0327", "caron": "\u030c",
}

_UNICODE_GLYPH_RE = re.compile(r"^uni([0-9A-Fa-f]{4,6})$")
_U_GLYPH_RE = re.compile(r"^u([0-9A-Fa-f]{4,6})$")


def glyph_to_unicode(name):
    if not name:
        return None
    if name in _STANDARD_GLYPHS:
        return _STANDARD_GLYPHS[name]
    if len(name) == 1:
        return name
    if name in _GREEK:
        return _GREEK[name]
    m = _UNICODE_GLYPH_RE.match(name) or _U_GLYPH_RE.match(name)
    if m:
        try:
            return chr(int(m.group(1), 16))
        except ValueError:
            return None
    m = re.match(r"^([A-Za-z])" + "(" + "|".join(_ACCENTS) + r")$", name)
    if m:
        import unicodedata
        return unicodedata.normalize("NFC", m.group(1) + _ACCENTS[m.group(2)])
    m = re.match(r"^([a-zA-Z]+)\.(sc|alt|swash|frac|oldstyle)$", name)
    if m:
        return glyph_to_unicode(m.group(1))
    m = re.match(r"^(?:g|cid|c|glyph)(\d+)$", name)
    if m:
        return None
    return None


def _parse_cmap(data):
    """Return (mapping dict, code byte widths list)."""
    mapping = {}
    widths = set()
    text = data
    for m in re.finditer(rb"begincodespacerange(.*?)endcodespacerange", text, re.S):
        for lo in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", m.group(1)):
            widths.add(len(lo.group(1)) // 2)
    for m in re.finditer(rb"beginbfchar(.*?)endbfchar", text, re.S):
        for pair in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", m.group(1)):
            src = int(pair.group(1), 16)
            widths.add(len(pair.group(1)) // 2)
            dst = pair.group(2).decode("ascii")
            mapping[src] = _utf16be(dst)
    for m in re.finditer(rb"beginbfrange(.*?)endbfrange", text, re.S):
        body = m.group(1)
        for rng in re.finditer(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<([0-9A-Fa-f]*)>|\[(.*?)\])",
            body, re.S,
        ):
            lo = int(rng.group(1), 16)
            hi = int(rng.group(2), 16)
            widths.add(len(rng.group(1)) // 2)
            if hi < lo or hi - lo > 65536:
                continue
            if rng.group(4) is not None:
                base = _utf16be(rng.group(4).decode("ascii"))
                if not base:
                    continue
                head, last = base[:-1], base[-1]
                for offset in range(hi - lo + 1):
                    mapping[lo + offset] = head + chr(ord(last) + offset)
            else:
                items = re.findall(rb"<([0-9A-Fa-f]*)>", rng.group(5))
                for offset, item in enumerate(items):
                    mapping[lo + offset] = _utf16be(item.decode("ascii"))
    if not widths:
        widths = {1}
    return mapping, sorted(widths)


def _utf16be(hexstr):
    if not hexstr:
        return ""
    if len(hexstr) % 4 == 0:
        out = []
        for i in range(0, len(hexstr), 4):
            try:
                out.append(chr(int(hexstr[i:i + 4], 16)))
            except ValueError:
                pass
        return "".join(out)
    try:
        return chr(int(hexstr, 16))
    except ValueError:
        return ""


class Font:
    def __init__(self, doc, spec):
        self.name = ""
        self.cmap = {}
        self.code_widths = [1]
        self.simple_map = {}
        self.composite = False
        self.vertical = False
        self.widths = {}
        self.default_width = 500
        self.scale = 0.001
        spec = doc.resolve(spec)
        if not isinstance(spec, dict):
            return
        subtype = str(spec.get("Subtype", ""))
        self.composite = subtype == "Type0"
        enc = doc.resolve(spec.get("Encoding"))
        if isinstance(enc, dict) and str(enc.get("Type")) == "Encoding":
            diffs = doc.resolve(enc.get("Differences"))
            if isinstance(diffs, list):
                code = 0
                for item in diffs:
                    item = doc.resolve(item)
                    if isinstance(item, int):
                        code = item
                    elif isinstance(item, Name):
                        ch = glyph_to_unicode(str(item))
                        if ch is not None:
                            self.simple_map[code] = ch
                        code += 1
        tu = doc.resolve(spec.get("ToUnicode"))
        if isinstance(tu, dict):
            try:
                mapping, widths = _parse_cmap(doc._stream_data(tu))
                self.cmap = mapping
                if widths:
                    self.code_widths = widths
            except Exception:
                pass
        if self.composite and not self.cmap and self.code_widths == [1]:
            self.code_widths = [2]
        desc = doc.resolve(spec.get("FontDescriptor"))
        dw = spec.get("DW")
        if isinstance(dw, (int, float)):
            self.default_width = float(dw)
        elif isinstance(desc, dict) and isinstance(desc.get("MissingWidth"), (int, float)):
            self.default_width = float(desc.get("MissingWidth"))
        w = doc.resolve(spec.get("W"))
        if isinstance(w, list):
            i = 0
            while i < len(w):
                first = doc.resolve(w[i])
                nxt = doc.resolve(w[i + 1]) if i + 1 < len(w) else None
                if not isinstance(first, int):
                    break
                if isinstance(nxt, list):
                    for k, val in enumerate(nxt):
                        val = doc.resolve(val)
                        if isinstance(val, (int, float)):
                            self.widths[first + k] = float(val)
                    i += 2
                elif isinstance(nxt, int) and i + 2 < len(w):
                    val = doc.resolve(w[i + 2])
                    if isinstance(val, (int, float)):
                        for c in range(first, min(nxt, first + 4096) + 1):
                            self.widths[c] = float(val)
                    i += 3
                else:
                    break
        first_char = spec.get("FirstChar")
        wids = doc.resolve(spec.get("Widths"))
        if isinstance(first_char, int) and isinstance(wids, list):
            for k, val in enumerate(wids):
                val = doc.resolve(val)
                if isinstance(val, (int, float)):
                    self.widths[first_char + k] = float(val)

    def decode(self, raw):
        """Yield (text, code, code_width_bytes) triples."""
        out = []
        if self.cmap:
            i = 0
            n = len(raw)
            while i < n:
                matched = False
                for width in self.code_widths:
                    if i + width > n:
                        continue
                    code = int.from_bytes(raw[i:i + width], "big")
                    if code in self.cmap:
                        out.append((self.cmap[code], code, width))
                        i += width
                        matched = True
                        break
                if not matched:
                    width = self.code_widths[-1] if self.code_widths else 1
                    code = int.from_bytes(raw[i:i + width], "big")
                    out.append((self.simple_map.get(code, ""), code, width))
                    i += width
            return out
        if self.composite:
            i = 0
            while i + 2 <= len(raw):
                code = int.from_bytes(raw[i:i + 2], "big")
                out.append((self.simple_map.get(code, ""), code, 2))
                i += 2
            return out
        for byte in raw:
            ch = self.simple_map.get(byte)
            if ch is None:
                try:
                    ch = bytes([byte]).decode("cp1252")
                except UnicodeDecodeError:
                    ch = ""
            out.append((ch, byte, 1))
        return out

    def width_of(self, code, width_bytes):
        if width_bytes == 2:
            return self.widths.get(code, self.default_width) * 0.001
        return self.widths.get(code, self.default_width) * 0.001


# ---------------------------------------------------------------- content

class Glyph:
    __slots__ = ("text", "x", "y", "size", "font", "seq", "w", "rot")

    def __init__(self, text, x, y, size, font, seq, w, rot=0):
        self.text = text
        self.x = x
        self.y = y
        self.size = size
        self.font = font
        self.seq = seq
        self.w = w
        self.rot = rot

    def __repr__(self):
        return "G(%r,%.1f,%.1f,%.1f)" % (self.text, self.x, self.y, self.size)


def _mul(a, b):
    return [
        a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5],
    ]


IDENTITY = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


class ContentExtractor:
    def __init__(self, doc):
        self.doc = doc
        self._font_cache = {}

    def _fonts(self, resources):
        cache_key = id(resources)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        fonts = {}
        res = self.doc.resolve(resources)
        if isinstance(res, dict):
            fdict = self.doc.resolve(res.get("Font"))
            if isinstance(fdict, dict):
                for key, val in fdict.items():
                    fonts[key] = Font(self.doc, val)
        self._font_cache[cache_key] = fonts
        return fonts

    def extract(self, page):
        data = self.doc.page_content(page)
        fonts = self._fonts(page.get("Resources"))
        glyphs = []
        seq = [0]
        self._run(data, fonts, glyphs, seq)
        return glyphs

    def _run(self, data, fonts, glyphs, seq):
        lex = Lexer(data, 0)
        stack = []
        ctm = list(IDENTITY)
        gstack = []
        tm = list(IDENTITY)
        tlm = list(IDENTITY)
        font = None
        fsize = 0.0
        leading = 0.0
        char_space = 0.0
        word_space = 0.0
        hscale = 1.0
        rise = 0.0
        while True:
            lex.skip_ws()
            if lex.p >= lex.n:
                break
            start = lex.p
            try:
                tok = lex.parse_object()
            except Exception:
                lex.p = start + 1
                continue
            if tok is None:
                continue
            if isinstance(tok, tuple) and tok[0] == "kw":
                op = tok[1]
                if op == "BI":
                    end = data.find(b"EI", lex.p)
                    lex.p = (end + 2) if end > 0 else lex.n
                    stack = []
                    continue
                if op == "q":
                    gstack.append((list(ctm), font, fsize, leading, char_space, word_space, hscale, rise))
                elif op == "Q":
                    if gstack:
                        ctm, font, fsize, leading, char_space, word_space, hscale, rise = gstack.pop()
                elif op == "cm" and len(stack) >= 6:
                    m = [float(v) for v in stack[-6:] if isinstance(v, (int, float))]
                    if len(m) == 6:
                        ctm = _mul(m, ctm)
                elif op == "BT":
                    tm = list(IDENTITY)
                    tlm = list(IDENTITY)
                elif op == "ET":
                    pass
                elif op == "Tf" and len(stack) >= 2:
                    name = stack[-2]
                    font = fonts.get(str(name)) if isinstance(name, Name) else fonts.get(name)
                    fsize = float(stack[-1]) if isinstance(stack[-1], (int, float)) else 0.0
                elif op == "TL" and stack and isinstance(stack[-1], (int, float)):
                    leading = float(stack[-1])
                elif op == "Tc" and stack and isinstance(stack[-1], (int, float)):
                    char_space = float(stack[-1])
                elif op == "Tw" and stack and isinstance(stack[-1], (int, float)):
                    word_space = float(stack[-1])
                elif op == "Tz" and stack and isinstance(stack[-1], (int, float)):
                    hscale = float(stack[-1]) / 100.0
                elif op == "Ts" and stack and isinstance(stack[-1], (int, float)):
                    rise = float(stack[-1])
                elif op in ("Td", "TD") and len(stack) >= 2:
                    tx = float(stack[-2]) if isinstance(stack[-2], (int, float)) else 0.0
                    ty = float(stack[-1]) if isinstance(stack[-1], (int, float)) else 0.0
                    if op == "TD":
                        leading = -ty
                    tlm = _mul([1, 0, 0, 1, tx, ty], tlm)
                    tm = list(tlm)
                elif op == "Tm" and len(stack) >= 6:
                    vals = [float(v) for v in stack[-6:] if isinstance(v, (int, float))]
                    if len(vals) == 6:
                        tlm = vals
                        tm = list(tlm)
                elif op == "T*":
                    tlm = _mul([1, 0, 0, 1, 0, -leading], tlm)
                    tm = list(tlm)
                elif op in ("Tj", "'", '"', "TJ"):
                    if op == "'":
                        tlm = _mul([1, 0, 0, 1, 0, -leading], tlm)
                        tm = list(tlm)
                    if op == '"' and len(stack) >= 3:
                        if isinstance(stack[-3], (int, float)):
                            word_space = float(stack[-3])
                        if isinstance(stack[-2], (int, float)):
                            char_space = float(stack[-2])
                        tlm = _mul([1, 0, 0, 1, 0, -leading], tlm)
                        tm = list(tlm)
                    payload = stack[-1] if stack else None
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        if isinstance(item, bytes):
                            tm = self._show(item, font, fsize, char_space, word_space,
                                            hscale, rise, tm, ctm, glyphs, seq)
                        elif isinstance(item, (int, float)):
                            shift = -float(item) / 1000.0 * fsize * hscale
                            tm = _mul([1, 0, 0, 1, shift, 0], tm)
                stack = []
                continue
            stack.append(tok)
            if len(stack) > 64:
                stack = stack[-64:]

    def _show(self, raw, font, fsize, char_space, word_space, hscale, rise, tm, ctm, glyphs, seq):
        if font is None:
            font = Font(self.doc, {})
        for text, code, width_bytes in font.decode(raw):
            trm = _mul(_mul([fsize * hscale, 0, 0, fsize, 0, rise], tm), ctm)
            x, y = trm[4], trm[5]
            a, b = trm[0], trm[1]
            scale = math.hypot(a, b)
            size = scale or fsize
            rot = math.degrees(math.atan2(b, a)) if (a or b) else 0.0
            adv = font.width_of(code, width_bytes) * fsize + char_space
            if width_bytes == 1 and code == 32:
                adv += word_space
            shown = adv * hscale
            if text:
                seq[0] += 1
                glyphs.append(Glyph(text, x, y, size, id(font), seq[0], shown, rot))
            tm = _mul([1, 0, 0, 1, shown, 0], tm)
        return tm


# ---------------------------------------------------------------- layout

class TextLine:
    __slots__ = ("text", "x", "y", "size", "x0", "x1", "col", "page", "glyphs")

    def __init__(self, text, x, y, size, x0, x1, page, glyphs):
        self.text = text
        self.x = x
        self.y = y
        self.size = size
        self.x0 = x0
        self.x1 = x1
        self.col = 0
        self.page = page
        self.glyphs = glyphs

    def __repr__(self):
        return "L(y=%.1f,x=%.1f,%r)" % (self.y, self.x, self.text[:24])


def _rot_bucket(rot):
    """Snap a glyph rotation to the nearest axis (0/90/180/270)."""
    r = (rot + 45.0) % 180.0
    if r >= 90.0:
        return 90
    return 0


def glyphs_to_lines(glyphs, page_no, y_tol_ratio=0.55):
    """Group glyphs into text lines, discarding non-horizontal runs.

    Rotated runs on scientific PDFs are almost always margin stamps
    (arXiv's ``arXiv:1706.03762v7 [cs.CL] 2 Aug 2023`` banner) or figure
    axis labels. Mixing them into body rows corrupts both the text and the
    reading order, so they are dropped rather than re-sorted.
    """
    if not glyphs:
        return []
    horiz = [g for g in glyphs if _rot_bucket(g.rot) == 0]
    if len(horiz) < len(glyphs) * 0.25:
        horiz = list(glyphs)
    ordered = sorted(horiz, key=lambda g: (-round(g.y, 1), g.x))
    rows = []
    for g in ordered:
        placed = False
        for row in rows[-6:]:
            ref = row[0]
            tol = max(0.6, min(ref.size, g.size) * y_tol_ratio)
            if abs(ref.y - g.y) > tol:
                continue
            # Same baseline is not enough: a two-column page puts unrelated
            # columns on the same y. Only join when the glyph sits next to an
            # existing member instead of across the gutter.
            if _horiz_gap(row, g) <= max(ref.size, g.size) * 3.0:
                row.append(g)
                placed = True
                break
        if not placed:
            rows.append([g])
    lines = []
    for row in rows:
        row.sort(key=lambda g: (g.x, g.seq))
        text = _join_glyphs(row)
        if not text.strip():
            continue
        sizes = [g.size for g in row if g.text.strip()]
        size = max(sizes) if sizes else row[0].size
        xs0 = min(g.x for g in row)
        xs1 = max(g.x + (g.w if g.w > 0 else g.size * 0.5) for g in row)
        lines.append(TextLine(text, row[0].x, row[0].y, size, xs0, xs1, page_no, row))
    lines.sort(key=lambda l: (-l.y, l.x))
    return lines


def _horiz_gap(row, g):
    """Smallest horizontal distance from ``g`` to any glyph already in ``row``."""
    best = None
    for o in row:
        gap = g.x - (o.x + o.w)
        if gap < 0:
            gap = o.x - (g.x + g.w)
        if gap < 0:
            gap = 0.0
        if best is None or gap < best:
            best = gap
    return best if best is not None else 0.0


def _join_glyphs(row):
    out = []
    prev = None
    for g in row:
        if prev is not None and not out[-1].endswith(" ") and not g.text.startswith(" "):
            gap = g.x - (prev.x + prev.w)
            if gap > max(prev.size, g.size) * 0.12:
                out.append(" ")
        out.append(g.text)
        prev = g
    return "".join(out)


def detect_columns(lines, page_width):
    """Assign a column index per line using x-center clustering on body lines."""
    if not lines:
        return 1
    body = [l for l in lines if l.x1 - l.x0 > 0]
    if not body:
        return 1
    centers = sorted((l.x0 + l.x1) / 2.0 for l in body)
    if len(centers) < 6:
        return 1
    # gap analysis on left edges: two-column papers show a wide empty gutter
    lefts = sorted(l.x0 for l in body)
    width = page_width or max(l.x1 for l in body)
    span = max(1.0, width)
    hist = [0] * 60
    for l in body:
        b0 = int(max(0, min(59, l.x0 / span * 60)))
        b1 = int(max(0, min(59, l.x1 / span * 60)))
        for b in range(b0, b1 + 1):
            hist[b] += 1
    mid_lo, mid_hi = 22, 38
    gutter_empty = all(hist[b] <= max(1, len(body) // 40) for b in range(mid_lo, mid_hi))
    # count lines starting in left half vs right half
    left_lines = sum(1 for l in body if (l.x0 + l.x1) / 2 < width * 0.42)
    right_lines = sum(1 for l in body if (l.x0 + l.x1) / 2 > width * 0.42)
    full_lines = sum(1 for l in body if (l.x1 - l.x0) > width * 0.62)
    if gutter_empty and left_lines >= 4 and right_lines >= 4 and full_lines <= len(body) * 0.35:
        return 2
    if left_lines >= 4 and right_lines >= 4 and full_lines <= len(body) * 0.2:
        return 2
    return 1


def order_reading(lines, ncols, page_width):
    """Sort lines into human reading order for a detected column count."""
    if ncols <= 1 or not lines:
        for l in lines:
            l.col = 0
        return sorted(lines, key=lambda l: (-l.y, l.x))
    width = page_width or max(l.x1 for l in lines)
    split = width * 0.5
    for l in lines:
        cx = (l.x0 + l.x1) / 2.0
        wide = (l.x1 - l.x0) > width * 0.62
        if wide:
            l.col = -1  # full width: belongs to the flow at its own y
        else:
            l.col = 0 if cx < split else 1
    # split the page into horizontal bands separated by full-width lines
    bands = []
    current = {0: [], 1: []}
    for l in sorted(lines, key=lambda l: (-l.y, l.x)):
        if l.col == -1:
            bands.append(("cols", current))
            bands.append(("wide", [l]))
            current = {0: [], 1: []}
        else:
            current[l.col].append(l)
    bands.append(("cols", current))
    out = []
    for kind, payload in bands:
        if kind == "wide":
            out.extend(payload)
        else:
            out.extend(sorted(payload[0], key=lambda l: (-l.y, l.x)))
            out.extend(sorted(payload[1], key=lambda l: (-l.y, l.x)))
    return out


class PageLayout:
    def __init__(self, page_no, width, height, lines, ncols, rotation):
        self.page_no = page_no
        self.width = width
        self.height = height
        self.lines = lines
        self.ncols = ncols
        self.rotation = rotation

    def text(self):
        return "\n".join(l.text for l in self.lines)


def _page_box(doc, page):
    box = doc.resolve(page.get("CropBox")) or doc.resolve(page.get("MediaBox"))
    if isinstance(box, list) and len(box) >= 4:
        vals = []
        for v in box[:4]:
            v = doc.resolve(v)
            vals.append(float(v) if isinstance(v, (int, float)) else 0.0)
        return vals
    return [0.0, 0.0, 612.0, 792.0]


def extract_layout(data):
    """Return list[PageLayout] for the whole document."""
    doc = Document(data)
    ex = ContentExtractor(doc)
    out = []
    for i, page in enumerate(doc.pages()):
        box = _page_box(doc, page)
        width = abs(box[2] - box[0])
        height = abs(box[3] - box[1])
        rot = doc.resolve(page.get("Rotate"))
        rot = int(rot) if isinstance(rot, int) else 0
        try:
            glyphs = ex.extract(page)
        except Exception:
            glyphs = []
        lines = glyphs_to_lines(glyphs, i)
        ncols = detect_columns(lines, width)
        ordered = order_reading(lines, ncols, width)
        out.append(PageLayout(i, width, height, ordered, ncols, rot))
    return out
