# shortlink

URL shortener. Turns a long URL into a 6-character code. Flask + SQLite.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Endpoints

```
POST /api/shorten      { "url": "https://..." }
GET  /api/links
GET  /api/links/<code>
DEL  /api/links/<code>
GET  /<code>           redirect
```

## Input checks on shorten

- scheme must be http or https
- max 2048 characters
- localhost and private IPs rejected
- port must be 1-65535
- control characters rejected

Codes come from `secrets`, not `random`, and not sequential integers, so they can't be guessed.

URLs are run through `html.escape` before rendering so the page doesn't break.

## Test

```bash
curl -X POST http://localhost:5000/api/shorten -H "Content-Type: application/json" -d "{\"url\":\"https://www.google.com\"}"
```

```bash
curl -X POST http://localhost:5000/api/shorten -H "Content-Type: application/json" -d "{\"url\":\"http://127.0.0.1/admin\"}"
```

Second one gets rejected.

## Todo

- no user accounts, anyone can list every link
- delete only via API, no button in the UI
- no expiry
- no custom codes
