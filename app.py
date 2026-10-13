import os
import re
import sqlite3
import string
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    abort,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("SHORTLINK_DB", os.path.join(BASE_DIR, "shortlink.db"))

ALPHABET = string.digits + string.ascii_letters
CODE_LENGTH = 6
MAX_URL_LENGTH = 2048
MAX_ATTEMPTS = 5

ALLOWED_SCHEMES = ("http", "https")

BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
}

app = Flask(__name__)
app.config["DATABASE"] = DATABASE

def get_db():
    if "db" not in g:
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS links (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    NOT NULL UNIQUE,
                url         TEXT    NOT NULL,
                clicks      INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_links_code ON links(code);
            """
        )
        conn.commit()
    finally:
        conn.close()

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def generate_code(length= CODE_LENGTH):
    return "".join(secrets.choice(ALPHABET) for _ in range(length))

def valid_code(code):
    return bool(re.fullmatch(r"[0-9A-Za-z]{1,32}", code or ""))

def unique_code(db, attempts=10):
    length = CODE_LENGTH
    for i in range(attempts):
        code = generate_code(length)
        row = db.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone()
        if row is None:
            return code
        if i >= attempts // 2:
            length += 2
    raise RuntimeError("gagal membuat kode unik, coba lagi")

def validate_url(raw):
    if raw is None or not isinstance(raw, str):
        return None, "urlnya belum diisi"

    url = raw.strip()
    if not url:
        return None, "urlnya kosong"

    if len(url) > MAX_URL_LENGTH:
        return None, f"urlnya kepanjangan, maksimal {MAX_URL_LENGTH} karakter"

    if any(ch in url for ch in ("\n", "\r", "\t", "\x00")):
        return None, "urlnya ada karakter aneh"

    scheme_match = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", url)
    if scheme_match:
        scheme = scheme_match.group(1).lower()
        if scheme not in ALLOWED_SCHEMES:
            return None, (
                f"skema '{scheme}' gak didukung, pake http:// atau https:// aja"
            )
    if "://" not in url:
        if re.match(r"^[A-Za-z0-9]", url):
            url = "http://" + url
        else:
            return None, "format urlnya gak bener"

    try:
        parsed = urlparse(url)
    except ValueError:
        return None, "format urlnya gak bener"

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return None, (
            f"skema '{parsed.scheme}' gak didukung, pake http:// atau https:// aja"
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None, "urlnya harus ada hostnya, contoh https://example.com"
    if host in BLOCKED_HOSTS:
        return None, f"host '{host}' gak boleh dipake"
    if "." not in host and ":" not in host:
        return None, f"host '{host}' kayaknya bukan domain yang bener"
    if len(host) > 253:
        return None, "nama hostnya kepanjangan"

    try:
        port = parsed.port
    except ValueError:
        return None, "nomor portnya gak bener"
    if port is not None and not (1 <= port <= 65535):
        return None, "nomor portnya di luar 1-65535"

    return url, None

def insert_link(db, url):
    code = unique_code(db)
    cur = db.execute(
        "INSERT INTO links (code, url, clicks, created_at) VALUES (?, ?, 0, ?)",
        (code, url, now_iso()),
    )
    db.commit()
    return db.execute("SELECT * FROM links WHERE id = ?", (cur.lastrowid,)).fetchone()

def link_to_dict(row: sqlite3.Row):
    code = row["code"]
    return {
        "code": code,
        "url": row["url"],
        "short_url": f"{request.host_url.rstrip('/')}/{code}",
        "clicks": row["clicks"],
        "created_at": row["created_at"],
    }

def wants_json():
    if request.path.startswith("/api/"):
        return True
    if request.is_json:
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept

def payload():
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict() or request.args.to_dict()

@app.route("/", methods=["GET"])
def index():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM links ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return render_template("index.html", links=[link_to_dict(r) for r in rows])

@app.route("/", methods=["POST"])
def create_from_form():
    data = payload()
    url, err = validate_url(data.get("url"))

    if err:
        db = get_db()
        rows = db.execute("SELECT * FROM links ORDER BY id DESC LIMIT 20").fetchall()
        return render_template(
            "index.html",
            links=[link_to_dict(r) for r in rows],
            error=err,
            submitted=data.get("url", ""),
        ), 400

    row = insert_link(get_db(), url)
    return redirect("/?created=" + row["code"])

@app.route("/api/links", methods=["GET"])
def api_list():
    limit_raw = request.args.get("limit", "50")
    try:
        limit = max(1, min(int(limit_raw), 200))
    except (TypeError, ValueError):
        return jsonify({"error": "parameter 'limit' harus angka"}), 400

    rows = get_db().execute(
        "SELECT * FROM links ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return jsonify({"count": len(rows), "links": [link_to_dict(r) for r in rows]})

@app.route("/api/shorten", methods=["POST"])
def api_shorten():
    data = payload()
    url, err = validate_url(data.get("url"))
    if err:
        return jsonify({"error": err}), 400

    row = insert_link(get_db(), url)
    return jsonify(link_to_dict(row)), 201

@app.route("/api/links/<code>", methods=["GET"])
def api_get(code):
    if not valid_code(code):
        return jsonify({"error": "kodenya gak valid"}), 400

    row = get_db().execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
    if row is None:
        return jsonify({"error": "kodenya gak ketemu"}), 404
    return jsonify(link_to_dict(row))

@app.route("/api/links/<code>", methods=["DELETE"])
def api_delete(code):
    if not valid_code(code):
        return jsonify({"error": "kodenya gak valid"}), 400

    db = get_db()
    cur = db.execute("DELETE FROM links WHERE code = ?", (code,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"error": "kodenya gak ketemu"}), 404
    return jsonify({"deleted": code}), 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "links": get_db().execute(
        "SELECT COUNT(*) AS n FROM links").fetchone()["n"]})

@app.route("/<code>", methods=["GET"])
def follow(code):
    if not valid_code(code):
        abort(404)

    db = get_db()
    row = db.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
    if row is None:
        abort(404)

    db.execute("UPDATE links SET clicks = clicks + 1 WHERE id = ?", (row["id"],))
    db.commit()

    return redirect(row["url"], code=302)

@app.errorhandler(404)
def not_found(e):
    if wants_json():
        return jsonify({"error": "Not found"}), 404
    return render_template("404.html"), 404

init_db()

if __name__ == "__main__":
    debug = os.environ.get("SHORTLINK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=debug)
