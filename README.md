# LTC Laptop ↔  Phone Connect

## Requirements

- Python 3.10+
- Laptop and phone on the same Wi‑Fi/LAN

## Install

```bash
cd phone_laptop_transfer
python -m venv .venv
````

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

### macOS / Linux

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Open

On the laptop, open:

```text
http://127.0.0.1:5000
```

The page will show a QR code. Scan it with your phone camera.

## Where files go

* Phone → Laptop uploads are saved in:

  * `uploads/`
* Laptop → Phone files are temporarily saved in:

  * `outgoing/`
* Pairing and transfer history are stored in:

  * `data/app.db`

## Notes

* This build uses **Flask** for the app server.
* It uses **SQLite** so SQL is part of the project.
* Phone side is a browser app for easier cross-platform use.
* For larger files, performance is mostly limited by your Wi‑Fi speed.

## Good next upgrades

* End-to-end encryption for files
* Resume interrupted transfers
* Drag-and-drop on laptop UI
* Multi-file upload queue
* Native Android/iOS wrapper
* WebSocket live updates instead of polling

```

---

## How the SQL requirement is satisfied

This project uses **SQLite** with SQL tables for:

- `pair_sessions`
- `devices`
- `transfers`

SQL is directly used in `app.py` through `CREATE TABLE`, `INSERT`, `SELECT`, and `UPDATE` statements.

---

## How to run

1. Create the folder tree exactly as shown.
2. Copy each code block into the matching file path.
3. Install dependencies from `requirements.txt`.
4. Run `python app.py` on the laptop.
5. Open `http://127.0.0.1:5000` on the laptop.
6. Scan the QR code with the phone.
7. Link the phone once.
8. Transfer files both directions.

---

## Important limitations

- This version works over the **same local network**.
- On iPhone, browser downloads follow Safari’s download behavior.
- On some networks, firewall rules may block the laptop port `5000`.
- This is a solid prototype / MVP, not yet a hardened production app.