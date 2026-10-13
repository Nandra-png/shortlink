# shortlink

url shortener, simpen url panjang jadi kode 6 karakter. flask + sqlite

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

buka `http://127.0.0.1:5000`

## endpoint

```
POST /api/shorten      { "url": "https://..." }
GET  /api/links
GET  /api/links/<kode>
DEL  /api/links/<kode>
GET  /<kode>           redirect
```

## yang dicek waktunya masukin url

- skema harus http atau https
- maksimal 2048 karakter
- host lokal sama ip dalam ditolak
- port harus 1-65535
- karakter kontrol ditolak

kodenya pake `secrets`, bukan `random` sama bukan urutan angka, jadi gak bisa ditebak

pas nampilin url di halaman pake `html.escape` biar html-nya gak rusak

## tes

```bash
curl -X POST http://localhost:5000/api/shorten -H "Content-Type: application/json" -d "{\"url\":\"https://www.google.com\"}"
```

```bash
curl -X POST http://localhost:5000/api/shorten -H "Content-Type: application/json" -d "{\"url\":\"http://127.0.0.1/admin\"}"
```

yang kedua ditolak

## todo

- gak ada user, sapaun bisa liat semua link
- hapus link cuma lewat api, gak ada di web
- gak ada expired
- gak bisa custom kode
