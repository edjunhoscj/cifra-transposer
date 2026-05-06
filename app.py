"""
Transpositor de Cifras PDF — Streamlit
Hospedado no Streamlit Community Cloud (gratuito).
"""

import re, io, os
import streamlit as st
import fitz  # pymupdf

# ================================================================
# MOTOR DE TRANSPOSIÇÃO
# ================================================================

NOTES_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
NOTES_FLAT  = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']
NOTE_SEMI   = {
    'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,
    'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11
}
FLAT_KEYS = {'F','Bb','Eb','Ab','Db','Gb','Fm','Bbm','Ebm','Abm','Dbm','Gbm'}

CHORD_RE = re.compile(
    r'^([A-G][#b]?)'
    r'(m(?:aj)?7?|min7?|M7?|maj7?|7|9|11|13|dim7?|aug|sus[24]?|add\d+|6|4|2)?'
    r'(\([^)]*\))?(\/[A-G][#b]?)?$'
)

def _semi(n):   return NOTE_SEMI.get(n, -1)
def _note(s,f): return (NOTES_FLAT if f else NOTES_SHARP)[((s%12)+12)%12]

def transpose_root(root, n, flat):
    s = _semi(root)
    return root if s < 0 else _note(s + n, flat)

def transpose_token(tok, n, flat):
    m = re.match(r'^([A-G][#b]?)([^/]*)(\/([A-G][#b]?)(.*))?$', tok)
    if not m: return tok
    new = transpose_root(m.group(1), n, flat) + (m.group(2) or '')
    if m.group(4):
        new += '/' + transpose_root(m.group(4), n, flat) + (m.group(5) or '')
    return new

def is_chord(tok):
    return bool(CHORD_RE.match(tok.strip()))

def key_interval(src, dst):
    def root(k):
        if k.endswith('m') and len(k) > 1 and not k.endswith(('maj','dim')):
            return k[:-1]
        return k
    a, b = _semi(root(src)), _semi(root(dst))
    return 0 if a < 0 or b < 0 else ((b - a) + 12) % 12

def detect_key(text):
    roots, first = [], None
    for line in text.split('\n'):
        tokens = line.strip().split()
        if not tokens or not re.match(r'^[A-G]', tokens[0]): continue
        hits = sum(1 for t in tokens if is_chord(t))
        if not tokens or hits / len(tokens) < 0.5: continue
        for t in tokens:
            m = re.match(r'^([A-G][#b]?)', t)
            if m and is_chord(t):
                roots.append(m.group(1))
                if first is None: first = m.group(1)
    if not roots: return 'C'
    counts = {}
    for r in roots: counts[r] = counts.get(r, 0) + 1
    if first: counts[first] = counts.get(first, 0) + 3
    return max(counts, key=counts.get)


# ================================================================
# EXTRAÇÃO E GRUPOS DE LINHAS
# ================================================================

def extract_spans(page):
    spans = []
    for blk in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if blk.get("type") != 0: continue
        for line in blk["lines"]:
            for sp in line["spans"]:
                if sp["text"].strip():
                    spans.append(sp)
    return spans

def group_lines(spans, y_tol=4):
    if not spans: return []
    s = sorted(spans, key=lambda x: (round(x["bbox"][1]/y_tol), x["bbox"][0]))
    lines, cur = [], [s[0]]
    for sp in s[1:]:
        if abs(sp["bbox"][1] - cur[-1]["bbox"][1]) <= y_tol * 2.5:
            cur.append(sp)
        else:
            lines.append(sorted(cur, key=lambda x: x["bbox"][0]))
            cur = [sp]
    lines.append(sorted(cur, key=lambda x: x["bbox"][0]))
    return lines

def is_chord_line(spans):
    tokens = [t for sp in spans for t in sp["text"].split()]
    if not tokens: return False
    hits = sum(1 for t in tokens if is_chord(t))
    return hits / len(tokens) >= 0.5 and bool(re.match(r'^[A-G]', tokens[0]))


# ================================================================
# TRANSPOSIÇÃO — PDF COM TEXTO (in-place via pymupdf)
# ================================================================

def transpose_text_pdf(doc, interval, flat):
    for page in doc:
        spans  = extract_spans(page)
        lines  = group_lines(spans)
        changes = []

        for line in lines:
            if not is_chord_line(line): continue
            for sp in line:
                tokens = sp["text"].split()
                new_tokens, changed = [], False
                for tok in tokens:
                    if is_chord(tok):
                        nt = transpose_token(tok, interval, flat)
                        new_tokens.append(nt)
                        if nt != tok: changed = True
                    else:
                        new_tokens.append(tok)
                if changed:
                    changes.append({
                        "rect":     fitz.Rect(sp["bbox"]),
                        "new_text": " ".join(new_tokens),
                        "size":     sp["size"],
                        "flags":    sp.get("flags", 0),
                        "color":    sp["color"],
                    })

        if not changes: continue

        for ch in changes:
            page.add_redact_annot(ch["rect"], fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        for ch in changes:
            flags  = ch["flags"]
            bold   = bool(flags & (1 << 4))
            italic = bool(flags & (1 << 1))
            if   bold and italic: fname = "courier-boldoblique"
            elif bold:            fname = "courier-bold"
            elif italic:          fname = "courier-oblique"
            else:                 fname = "courier"

            c_int = ch["color"]
            color = ((c_int>>16&0xFF)/255, (c_int>>8&0xFF)/255, (c_int&0xFF)/255)
            rect  = ch["rect"]
            page.insert_text(
                fitz.Point(rect.x0, rect.y1 - 1),
                ch["new_text"],
                fontname=fname,
                fontsize=ch["size"],
                color=color,
            )
    return doc


# ================================================================
# TRANSPOSIÇÃO — PDF ESCANEADO (OCR + overlay)
# ================================================================

def ocr_words_from_page(page, scale=2.5):
    try:
        import pytesseract
        from PIL import Image as PILImage
    except ImportError:
        return None

    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = PILImage.open(io.BytesIO(pix.tobytes("png")))
    data = pytesseract.image_to_data(img, lang="por+eng",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        if not txt or int(data["conf"][i]) < 25: continue
        words.append({
            "text": txt,
            "x0": data["left"][i] / scale,
            "y0": data["top"][i]  / scale,
            "x1": (data["left"][i] + data["width"][i])  / scale,
            "y1": (data["top"][i]  + data["height"][i]) / scale,
        })
    return words

def group_ocr_lines(words, y_tol=10):
    if not words: return []
    s = sorted(words, key=lambda w: (w["y0"], w["x0"]))
    lines, cur = [], [s[0]]
    for w in s[1:]:
        cy_p = (cur[-1]["y0"] + cur[-1]["y1"]) / 2
        cy_c = (w["y0"]      + w["y1"])       / 2
        if abs(cy_c - cy_p) <= y_tol:
            cur.append(w)
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur = [w]
    lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines

def transpose_scanned_pdf(doc, interval, flat):
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    c   = rl_canvas.Canvas(buf)

    for page in doc:
        pw, ph = page.rect.width, page.rect.height
        c.setPageSize((pw, ph))

        # Página original como fundo
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        c.drawImage(ImageReader(io.BytesIO(pix.tobytes("png"))),
                    0, 0, width=pw, height=ph, preserveAspectRatio=False)

        words = ocr_words_from_page(page)
        if not words:
            c.showPage()
            continue

        lines = group_ocr_lines(words)
        for line in lines:
            tokens = [w["text"] for w in line]
            if not tokens: continue
            hits = sum(1 for t in tokens if is_chord(t))
            if hits / len(tokens) < 0.5 or not re.match(r'^[A-G]', tokens[0]):
                continue
            for w in line:
                if not is_chord(w["text"]): continue
                transposed = transpose_token(w["text"], interval, flat)
                if transposed == w["text"]: continue

                x0, x1 = w["x0"], w["x1"]
                y0, y1 = w["y0"], w["y1"]
                h = y1 - y0
                rl_bot  = ph - y1
                rl_text = ph - y0 - h * 0.15

                c.setFillColorRGB(1, 1, 1)
                c.rect(x0-1, rl_bot-1, (x1-x0)+2, h+2, fill=1, stroke=0)
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Courier-Oblique", max(round(h * 0.72), 7))
                c.drawString(x0, rl_text, transposed)

        c.showPage()

    c.save()
    return buf.getvalue()


# ================================================================
# PIPELINE PRINCIPAL
# ================================================================

def has_text(doc, min_chars=60):
    return sum(len(p.get_text().strip()) for p in doc) >= min_chars

def run_transpose(pdf_bytes, from_key, to_key, progress_bar):
    interval = key_interval(from_key, to_key)
    flat     = to_key in FLAT_KEYS
    doc      = fitz.open(stream=pdf_bytes, filetype="pdf")

    progress_bar.progress(10, "Analisando PDF…")

    if has_text(doc):
        progress_bar.progress(30, "Transpondo PDF com texto…")
        transpose_text_pdf(doc, interval, flat)
        progress_bar.progress(90, "Salvando…")
        buf = io.BytesIO()
        doc.save(buf, garbage=4, deflate=True)
        result = buf.getvalue()
    else:
        progress_bar.progress(20, "PDF escaneado detectado — iniciando OCR…")
        try:
            result = transpose_scanned_pdf(doc, interval, flat)
        except ImportError as e:
            st.error(str(e))
            return None

    doc.close()
    progress_bar.progress(100, "Concluído!")
    return result


# ================================================================
# INTERFACE STREAMLIT
# ================================================================

MAJOR_KEYS = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
MINOR_KEYS = ['Cm','C#m','Dm','D#m','Em','Fm','F#m','Gm','G#m','Am','A#m','Bm']
ALL_KEYS   = MAJOR_KEYS + MINOR_KEYS

st.set_page_config(
    page_title="Transpositor de Cifras",
    page_icon="🎸",
    layout="centered",
)

st.title("🎸 Transpositor de Cifras PDF")
st.caption("Preserva a posição horizontal exata dos acordes · sem API · gratuito")

st.divider()

# Upload
uploaded = st.file_uploader(
    "Selecione a cifra em PDF",
    type=["pdf"],
    help="Suporta PDFs com texto e PDFs escaneados (OCR automático)"
)

if uploaded:
    pdf_bytes = uploaded.read()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_content = "\n".join(p.get_text() for p in doc)
    pdf_type = "com texto" if has_text(doc) else "escaneado (OCR)"
    doc.close()

    st.success(f"✅ **{uploaded.name}** carregado  ·  tipo: PDF {pdf_type}")

    # Detecta tom
    detected = detect_key(text_content)

    col1, col2 = st.columns(2)
    with col1:
        src = st.selectbox(
            "Tom de origem",
            ALL_KEYS,
            index=ALL_KEYS.index(detected) if detected in ALL_KEYS else 0,
            help="Detectado automaticamente — corrija se necessário"
        )
    with col2:
        # Sugere um tom diferente do detectado
        default_dst = ALL_KEYS[(ALL_KEYS.index(src) + 5) % len(ALL_KEYS)]
        dst = st.selectbox("Tom destino", ALL_KEYS,
                           index=ALL_KEYS.index(default_dst))

    if src == dst:
        st.warning("⚠️ Tom de origem e destino são iguais.")
    else:
        st.info(f"🎵 Transpor  **{src}  →  {dst}**")

        if st.button("🔀 Transpor e Baixar", type="primary", use_container_width=True):
            prog = st.progress(0, "Iniciando…")
            result = run_transpose(pdf_bytes, src, dst, prog)

            if result:
                out_name = uploaded.name.replace(".pdf", f"_tom_{dst}.pdf")
                st.download_button(
                    label=f"⬇️  Baixar  {out_name}",
                    data=result,
                    file_name=out_name,
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.balloons()

else:
    st.info("⬆️ Faça upload de um PDF de cifra para começar.")

st.divider()
st.caption(
    "Fonte aberta · "
    "[GitHub](https://github.com/edjunhoscj/cifra-transposer) · "
    "Funciona com PDF de texto e PDF escaneado"
)