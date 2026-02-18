from flask import Flask, render_template, Response
import requests

app = Flask(__name__)

FILE_ID = "1fYSiB-hhnNtmOYAFcHOWV7LLrD1K12rb"

def get_pdf_content(file_id):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    return None

@app.route("/")
def view_pdf():
    return render_template("result.html", file_id=FILE_ID)

@app.route("/pdf/<file_id>")
def serve_pdf(file_id):
    pdf_bytes = get_pdf_content(file_id)
    if not pdf_bytes:
        return "PDF not found", 404
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "inline; filename=report.pdf"}
    )

if __name__ == "__main__":
    app.run(debug=True)
