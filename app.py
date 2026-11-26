import asyncio
import os
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

app = FastAPI(title="Telegram Multi Sender")

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

# Temporary clients for login
login_clients = {}

def get_sessions():
    return sorted([f.stem for f in SESSIONS_DIR.glob("*.session") if not f.name.endswith(".session-journal")])

HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Telegram Multi Sender</title>
<style>
body { font-family: system-ui, Arial, sans-serif; background:#0f1115; color:#e6e6e6; margin:0; padding:20px; }
.container { max-width:800px; margin:0 auto; }
h1 { color:#5eead4; }
.card { background:#1a1d24; padding:20px; border-radius:12px; margin-bottom:20px; }
label { display:block; margin:12px 0 6px; font-weight:600; }
input, textarea, button { width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; font-size:15px; box-sizing:border-box; }
button { background:#14b8a6; color:#000; font-weight:bold; cursor:pointer; margin-top:10px; }
button:hover { background:#0d9488; }
.accounts { display:flex; flex-wrap:wrap; gap:10px; }
.account-item { background:#222; padding:8px 14px; border-radius:20px; }
#log { background:#111; padding:15px; border-radius:8px; height:200px; overflow:auto; font-family:monospace; white-space:pre-wrap; }
.success { color:#4ade80; } .error { color:#f87171; } .info { color:#60a5fa; }
</style>
</head>
<body>
<div class="container">
  <h1>Telegram Multi Sender</h1>

  <div class="card">
    <h3>Account hinzufügen</h3>
    <input id="phone" placeholder="+491701234567">
    <button onclick="startLogin()">Code anfordern</button>
    <div id="codeArea" style="display:none; margin-top:10px;">
      <input id="code" placeholder="Code aus Telegram">
      <input id="password" placeholder="2FA Passwort (falls vorhanden)" style="margin-top:8px;">
      <button onclick="finishLogin()">Einloggen</button>
    </div>
  </div>

  <div class="card">
    <form id="sendForm">
      <label>Accounts</label>
      <div class="accounts" id="accountList"></div>
      <label>Gruppen-Link</label>
      <input name="group" placeholder="https://t.me/gruppe" required>
      <label>Datei (optional)</label>
      <input type="file" name="file">
      <label>Text / Caption</label>
      <textarea name="caption" rows="3"></textarea>
      <label>Delay (Sekunden)</label>
      <input type="number" name="delay" value="8" min="3">
      <button type="submit">Senden</button>
    </form>
  </div>

  <div class="card">
    <div id="log">Bereit...</div>
  </div>
</div>

<script>
async function loadAccounts() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  const container = document.getElementById('accountList');
  if (!sessions.length) {
    container.innerHTML = '<p>Keine Accounts. Füge oben einen hinzu.</p>';
    return;
  }
  container.innerHTML = sessions.map(s => `
    <label class="account-item">
      <input type="checkbox" name="accounts" value="${s}" checked> ${s}
    </label>
  `).join('');
}

function log(msg, type='info') {
  const el = document.getElementById('log');
  el.innerHTML += `<div class="${type}">${msg}</div>`;
  el.scrollTop = el.scrollHeight;
}

async function startLogin() {
  const phone = document.getElementById('phone').value.trim();
  if (!phone) return alert('Nummer eingeben');
  const res = await fetch('/login/start', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({phone})
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('codeArea').style.display = 'block';
    log('Code wurde gesendet. Schau in Telegram.', 'success');
  } else {
    log(data.error || 'Fehler', 'error');
  }
}

async function finishLogin() {
  const phone = document.getElementById('phone').value.trim();
  const code = document.getElementById('code').value.trim();
  const password = document.getElementById('password').value.trim();
  const res = await fetch('/login/finish', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({phone, code, password})
  });
  const data = await res.json();
  if (data.ok) {
    log('Account hinzugefügt: ' + data.name, 'success');
    document.getElementById('codeArea').style.display = 'none';
    loadAccounts();
  } else {
    log(data.error || 'Fehler', 'error');
  }
}

document.getElementById('sendForm').onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = new FormData(form);
  const checked = [...document.querySelectorAll('input[name="accounts"]:checked')].map(i => i.value);
  if (!checked.length) return alert('Mindestens einen Account auswählen');
  data.delete('accounts');
  checked.forEach(a => data.append('accounts', a));
  log('Sende...', 'info');
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    const res = await fetch('/send', {method:'POST', body:data});
    const result = await res.json();
    result.results.forEach(r => log(r.message, r.ok ? 'success' : 'error'));
  } catch(err) { log('Fehler: '+err, 'error'); }
  btn.disabled = false;
};

loadAccounts();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML

@app.get("/sessions")
async def sessions():
    return get_sessions()

@app.post("/login/start")
async def login_start(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    if not phone:
        return {"ok": False, "error": "Keine Nummer"}
    try:
        session_name = phone.replace("+", "").replace(" ", "")
        client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
        await client.connect()
        await client.send_code_request(phone)
        login_clients[phone] = client
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

@app.post("/login/finish")
async def login_finish(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    code = data.get("code", "").strip()
    password = data.get("password", "").strip()
    client = login_clients.get(phone)
    if not client:
        return {"ok": False, "error": "Zuerst Code anfordern"}
    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        if not password:
            return {"ok": False, "error": "2FA Passwort nötig"}
        await client.sign_in(password=password)
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
    me = await client.get_me()
    await client.disconnect()
    login_clients.pop(phone, None)
    return {"ok": True, "name": me.first_name or phone}

@app.post("/send")
async def send(request: Request, group: str = Form(...), caption: str = Form(""), delay: int = Form(8), file: UploadFile = File(None)):
    form = await request.form()
    accounts = form.getlist("accounts")
    if not accounts:
        return {"results": [{"ok": False, "message": "Keine Accounts"}]}
    temp_path = None
    if file and file.filename:
        temp_path = tempfile.mktemp(suffix=Path(file.filename).suffix)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
    results = []
    for session_name in accounts:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            me = await client.get_me()
            name = me.first_name or session_name
            if temp_path:
                await client.send_file(group, temp_path, caption=caption or None)
                results.append({"ok": True, "message": f"[{name}] Datei gesendet"})
            elif caption:
                await client.send_message(group, caption)
                results.append({"ok": True, "message": f"[{name}] Text gesendet"})
            else:
                results.append({"ok": False, "message": f"[{name}] Nichts zum Senden"})
            await client.disconnect()
            await asyncio.sleep(delay)
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:100]}"})
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return {"results": results}

if __name__ == "__main__":
    print("Starte auf http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
