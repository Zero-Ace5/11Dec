import os
import uuid
from flask import Flask, request, redirect, render_template, send_file, url_for
from PIL import Image

UPLOAD_DIR = "uploads"
OUT_DIR = "resized"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

ALLOWED = {"png", "jpg", "jpeg"}


def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED


def parse_int(s):
    try:
        return int(s)
    except Exception:
        return None


app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            error = "NO FILE ADDED."
            return render_template("index.html", error=error)

        if not allowed(f.filename):
            error = "INVALID FILE."
            return render_template("index.html", error=error)

        keep_aspect = request.form.get("keep_aspect") == "on"
        w = parse_int(request.form.get("width", "").strip())
        h = parse_int(request.form.get("height", "").strip())

        if w is None and h is None:
            error = "At least one of width or height is needed."
            return render_template("index.html", error=error)

        ext = f.filename.rsplit(".", 1)[1].lower()
        in_name = f"{uuid.uuid4().hex}.{ext}"
        in_path = os.path.join(UPLOAD_DIR, in_name)
        f.save(in_path)

        img = Image.open(in_path)
        orig_w, orig_h = img.size

        if keep_aspect:
            if w and not h:
                new_w = w
                new_h = max(1, int((w/orig_w)*orig_h))
            elif h and not w:
                new_h = h
                new_w = max(1, int((h/orig_h) * orig_w))
            elif h and w:
                ratio = min(w/orig_w, h/orig_h)
                new_w = max(1, int(orig_w * ratio))
                new_h = max(1, int(orig_h * ratio))
            else:
                new_w, new_h = orig_w, orig_h
        else:
            new_w = w if w else orig_w
            new_h = h if h else orig_h

        resized = img.resize((new_w, new_h))

        out_name = f"{uuid.uuid4().hex}.{ext}"
        out_path = os.path.join(OUT_DIR, out_name)
        save_args = {"quality": 85} if ext in ("jpg", "jpeg") else {}

        resized.save(out_path, **save_args)

        result = {
            "orig_name": f.filename,
            "in_path": in_name,
            "out_name": out_name,
            "new_w": new_w,
            "new_h": new_h,
        }

        return render_template("index.html", result=result)
    return render_template("index.html")


@app.route("/uploads/<filename>")
def uploaded(filename):
    return send_file(os.path.join(UPLOAD_DIR, filename), as_attachment=False)


@app.route("/resized/<filename>")
def resized_file(filename):
    return send_file(os.path.join(OUT_DIR, filename), as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
