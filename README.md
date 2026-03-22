# HOW TO RUN THE SERVER

## 34) Create and activate virtual environment

### Windows PowerShell

```powershell
cd phone_laptop_transfer_pro\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 35) Generate encryption key

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the printed key.

## 36) Set environment variables and run

```powershell
$env:FERNET_KEY="PASTE_THE_KEY_HERE"
$env:APP_SECRET="replace-this-with-a-random-secret"
python app.py
```

Open on laptop:

```text
http://127.0.0.1:5000
```

---

# HOW TO BUILD WINDOWS EXE

Inside `phone_laptop_transfer_pro/server`:

```powershell
pip install pyinstaller
pyinstaller phone_laptop_transfer.spec
```

Your Windows executable will be created under:

```text
phone_laptop_transfer_pro/server/dist/TransferProServer.exe
```

---

# HOW TO BUILD ANDROID APK

1. Open `phone_laptop_transfer_pro/android` in Android Studio.
2. Let Gradle sync.
3. Build with:

   * **Build > Build APK(s)**
4. Install APK on Android phone.
5. Run the laptop server.
6. Open app on Android.
7. Scan or copy the QR token/server URL.
8. Pair once.
9. Upload/download files.

---

# IMPORTANT NOTES

## What is production-grade here

Compared to the earlier prototype, this version adds:

* resumable **chunked upload** from Android to laptop
* chunk-based **download** from laptop to Android
* **live updates** using Socket.IO on the laptop dashboard
* **encrypted pairing token** using Fernet
* **native Android app source** instead of browser only
* **Windows packaging** with PyInstaller
* improved UI styling

## What still needs hardening for real commercial release

This code is strong as a serious starter, but for a true commercial release you would still want:

* authenticated WebSocket namespaces per device
* TLS/HTTPS certificates instead of plain LAN HTTP
* transfer checksum verification per chunk and full file hash
* background Android transfer service with notifications
* persistent Android storage of device token using DataStore
* QR scanner screen embedded directly in app UI
* download resume bookkeeping stored locally on Android
* delta retry/backoff logic
* multi-device access controls
* desktop tray app and auto-start service
* installer creation for Windows using Inno Setup or MSIX