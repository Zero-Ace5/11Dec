import os
import uuid
from flask import Flask, render_template, url_for, request, redirect, send_from_directory, abort
from werkzeug.utils import secure_filename

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED = {"png", "jpeg", "jpg"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 20 * 1024


def allowed(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("files")
        for f in files:
            if not f or f.filename == "":
                continue
            if not allowed(f.filename):
                continue

            orig = secure_filename(f.filename)
            ext = orig.rsplit(".", 1)[1].lower()
            new_name = f"{uuid.uuid4().hex}.{ext}"

            f.save(os.path.join(UPLOAD_DIR, new_name))
        return redirect(url_for("index"))

    images = [fn for fn in sorted(os.listdir(
        UPLOAD_DIR), reverse=True) if allowed(fn)]
    return render_template("index.html", items=[{"name": n} for n in images])


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    safe = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe)

    if not os.path.exists(path):
        abort(404)
    return send_from_directory(UPLOAD_DIR, safe)


@app.route("/view/<filename>")
def view(filename):
    safe = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe)

    if not os.path.exists(path):
        abort(404)
    return render_template("view.html", filename=safe)


if __name__ == "__main__":
    app.run(debug=True)
