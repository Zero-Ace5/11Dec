import os
import uuid
from flask import Flask, request, render_template, send_file
from reportlab.pdfgen import canvas

app = Flask(__name__)

OUTPUT_DIR = "pdfs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_pdf(text):
    filename = f"{uuid.uuid4().hex}.pdf"
    path = os.path.join(OUTPUT_DIR, filename)

    c = canvas.Canvas(path)
    lines = text.split("\n")

    x = 50
    y = 800

    for line in lines:
        c.drawString(x, y, line)
        y -= 20

    c.save()
    return path, filename


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        text = request.form.get("text", "").strip()

        if not text:
            render_template("index.html", error="Enter something...")

        path, filename = create_pdf(text)

        return render_template("result.html", filename=filename)

    return render_template("index.html")


@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
