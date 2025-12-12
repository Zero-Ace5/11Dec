import os
import uuid
import json
import time
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, send_file, redirect, url_for
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.utils import ImageReader

# optional imports - handled gracefully
try:
    from PIL import Image
except Exception:
    Image = None

try:
    import docx  # python-docx
except Exception:
    docx = None

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

try:
    from pypdf import PdfMerger, PdfReader
except Exception:
    PdfMerger = None
    PdfReader = None

# configuration
UPLOAD_DIR = "uploads"
TMP_DIR = "tmp"
OUT_DIR = "out"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

app = Flask(__name__)

PAGE_SIZE = A4  # or letter


def save_upload_storage(file_storage):
    name = file_storage.filename or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    out_name = f"{uuid.uuid4().hex}"
    filename = f"{out_name}.{ext}" if ext else out_name
    path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(path)
    return path, name, ext


def extract_video_frame(video_path, out_image_path):
    """Try to extract a single frame using ffmpeg (first second)."""
    # requires ffmpeg on PATH
    cmd = [
        "ffmpeg", "-y", "-ss", "00:00:01", "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_image_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        return os.path.exists(out_image_path)
    except Exception:
        return False


def docx_to_text(path):
    """Extract text from docx if python-docx available."""
    if not docx:
        return None
    try:
        d = docx.Document(path)
        paragraphs = [p.text for p in d.paragraphs]
        return "\n".join(paragraphs)
    except Exception:
        return None


def get_audio_metadata(path):
    """Return a small dict with duration (seconds) and size if mutagen available."""
    info = {}
    try:
        if MutagenFile:
            m = MutagenFile(path)
            if m and m.info:
                duration = getattr(m.info, "length", None)
                if duration:
                    info["duration"] = round(duration, 1)
    except Exception:
        pass
    info["size_bytes"] = os.path.getsize(path)
    return info


def draw_text_wrapped(c, text, x, y, max_width, line_height=14):
    """Basic text wrapping for ReportLab canvas (monospace-ish)."""
    if not text:
        return y
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        current = words[0]
        for w in words[1:]:
            if stringWidth(current + " " + w, "Helvetica", 10) <= max_width:
                current = current + " " + w
            else:
                lines.append(current)
                current = w
        lines.append(current)
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
        if y < 50:
            c.showPage()
            y = PAGE_SIZE[1] - 50
    return y


def create_pdf_from_items(items, out_pdf_path):
    """
    items: list of dicts with keys:
      - type: 'text','image','audio','video','pdf','docx','other'
      - title: original filename
      - path: filesystem path
      - extra: optional metadata
    """
    c = canvas.Canvas(out_pdf_path, pagesize=PAGE_SIZE)
    w, h = PAGE_SIZE

    # cover page
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 70, "Converted Files")
    c.setFont("Helvetica", 10)
    y = h - 100
    for it in items:
        line = f"{it['title']}  —  {it['type']}"
        c.drawString(50, y, line)
        y -= 14
        if y < 60:
            c.showPage()
            y = h - 60

    c.showPage()

    # process each item
    for it in items:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, h - 50, f"File: {it['title']}")
        c.setFont("Helvetica", 10)
        c.drawString(50, h - 66, f"Type: {it['type']}")
        y = h - 90

        t = it["type"]
        p = it.get("path")

        if t == "text":
            # render text content
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                text = "(failed to read text file)"
            y = draw_text_wrapped(
                c, text, 50, y, max_width=w - 100, line_height=12)
            c.showPage()

        elif t == "image":
            if Image:
                try:
                    img = Image.open(p)
                    img_w, img_h = img.size
                    # compute scale to fit page area with margin
                    max_w = w - 100
                    max_h = h - 140
                    ratio = min(max_w / img_w, max_h / img_h, 1.0)
                    draw_w = img_w * ratio
                    draw_h = img_h * ratio
                    ir = ImageReader(img)
                    c.drawImage(ir, (w - draw_w) / 2, y - draw_h,
                                width=draw_w, height=draw_h)
                except Exception:
                    c.drawString(50, y, "(failed to render image)")
            else:
                c.drawString(50, y, "(Pillow not installed)")
            c.showPage()

        elif t == "video":
            # include a frame if extracted, else placeholder
            frame = it.get("frame_path")
            if frame and Image and os.path.exists(frame):
                try:
                    img = Image.open(frame)
                    img_w, img_h = img.size
                    max_w = w - 100
                    max_h = h - 140
                    ratio = min(max_w / img_w, max_h / img_h, 1.0)
                    draw_w = img_w * ratio
                    draw_h = img_h * ratio
                    ir = ImageReader(img)
                    c.drawImage(ir, 50, y - draw_h,
                                width=draw_w, height=draw_h)
                    y = y - draw_h - 20
                except Exception:
                    c.drawString(50, y, "(failed to render video frame)")
            else:
                c.drawString(
                    50, y, "(no frame extracted — ffmpeg missing or failed)")
                y -= 20
            # optionally show metadata
            meta = it.get("extra", {})
            if meta:
                c.drawString(50, y, f"Metadata: {json.dumps(meta)}")
            c.showPage()

        elif t == "audio":
            meta = it.get("extra", {})
            c.drawString(50, y, f"Filename: {it['title']}")
            y -= 16
            if meta:
                c.drawString(50, y, f"Metadata: {json.dumps(meta)}")
                y -= 16
            c.drawString(
                50, y, "Note: audio is not embedded — only metadata/name shown.")
            c.showPage()

        elif t == "docx":
            text = it.get("extra_text")
            if text:
                y = draw_text_wrapped(
                    c, text, 50, y, max_width=w - 100, line_height=12)
            else:
                c.drawString(50, y, "(failed to extract docx text)")
            c.showPage()

        elif t == "pdf":
            # we'll merge PDFs later (skip embedding pages here)
            c.drawString(
                50, y, "This PDF will be merged into the final document.")
            c.showPage()
        else:
            c.drawString(
                50, y, "(unknown file type — file included as metadata)")
            c.showPage()

    c.save()

    # If there are input PDFs and pypdf available, merge them in order:
    pdfs_to_merge = [out_pdf_path]
    for it in items:
        if it["type"] == "pdf":
            pdfs_to_merge.append(it["path"])

    if len(pdfs_to_merge) > 1 and PdfMerger:
        try:
            merger = PdfMerger()
            for p in pdfs_to_merge:
                merger.append(p)
            merger.write(out_pdf_path + ".merged")
            merger.close()
            os.replace(out_pdf_path + ".merged", out_pdf_path)
        except Exception:
            # merging failed — keep the original file
            pass

    return out_pdf_path


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded = request.files.getlist("files")
        if not uploaded:
            return render_template("index.html", error="Upload at least one file.")

        items = []
        # process uploads
        for f in uploaded:
            path, original_name, ext = save_upload_storage(f)
            typ = ext.lower()
            entry = {"type": "other", "title": original_name, "path": path}
            if typ in ("txt", "text"):
                entry["type"] = "text"
            elif typ in ("jpg", "jpeg", "png", "webp", "bmp", "gif"):
                entry["type"] = "image"
            elif typ in ("mp3", "wav", "m4a", "flac", "aac", "ogg"):
                entry["type"] = "audio"
                entry["extra"] = get_audio_metadata(path)
            elif typ in ("mp4", "mov", "mkv", "webm", "avi"):
                entry["type"] = "video"
            elif typ in ("docx",):
                entry["type"] = "docx"
                if docx:
                    try:
                        entry["extra_text"] = docx_to_text(path)
                    except Exception:
                        entry["extra_text"] = None
            elif typ in ("pdf",):
                entry["type"] = "pdf"
            else:
                entry["type"] = "other"
            items.append(entry)

        # attempt to extract video frames for videos
        for it in items:
            if it["type"] == "video":
                base = os.path.join(TMP_DIR, uuid.uuid4().hex + ".jpg")
                ok = extract_video_frame(it["path"], base)
                if ok:
                    it["frame_path"] = base
                else:
                    it["frame_path"] = None

        # build PDF
        out_name = f"{uuid.uuid4().hex}.pdf"
        out_path = os.path.join(OUT_DIR, out_name)
        pdf_path = create_pdf_from_items(items, out_path)

        return redirect(url_for("download", filename=os.path.basename(pdf_path)))

    return render_template("index.html")


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUT_DIR, filename)
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
