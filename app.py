import asyncio
import os
import tempfile
import secrets
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_SECRET_PATH = os.getenv("ADMIN_SECRET_PATH", "admin-secret")  # geheime URL

app = FastAPI(title="Telegram Multi Sender")

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

login_clients = {}
sessions_tokens = {}

def get_sessions():
    return sorted([f.stem for f in SESSIONS_DIR.glob("*.session") if not f.name.endswith(".session-journal")])

def check_auth(request: Request):
    token = request.cookies.get("auth_token")
    return token in sessions_tokens

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Login</title>
<style>
body { font-family: system-ui, Arial; background:#0f1115; color:#e6e6e6; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
.box { background:#1a1d24; padding:40px; border-radius:16px; width:360px; text-align:center; }
h1 { color:#5eead4; }
input { width:100%; padding:12px; margin:10px 0; border-radius:8px; border:1px solid #333; background:#111; color:#fff; font-size:16px; box-sizing:border-box; }
button { width:100%; padding:12px; background:#14b8a6; color:#000; font-weight:bold; border:none; border-radius:8px; cursor:pointer; font-size:16px; }
.error { color:#f87171; margin-top:10px; }
</style>
</head>
<body>
<div class="box">
  <h1>Login</h1>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="Passwort" required autofocus>
    <button type="submit">Einloggen</button>
  </form>
  ERROR_PLACEHOLDER
</div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Dashboard</title>
<style>
body { font-family: system-ui, Arial; background:#0f1115; color:#e6e6e6; margin:0; padding:20px; }
.container { max-width:800px; margin:0 auto; }
h1 { color:#5eead4; }
.verified { background:#065f46; color:#6ee7b7; padding:10px 16px; border-radius:8px; display:inline-block; margin-bottom:20px; }
.nav { margin:20px 0; }
.nav a { background:#1a1d24; color:#5eead4; padding:12px 24px; border-radius:8px; text-decoration:none; margin-right:10px; display:inline-block; }
.nav a:hover { background:#222; }
.logout { float:right; background:#dc2626; color:#fff; padding:8px 16px; border-radius:8px; text-decoration:none; }
</style>
</head>
<body>
<div class="container">
  <a href="/logout" class="logout">Logout</a>
  <h1>Dashboard</h1>
  <div class="verified">Verifiziert ✓</div>
  <div class="nav">
    <a href="/sender">Sender</a>
  </div>
  <p>Hier kannst du Nachrichten und Dateien senden.</p>
</div>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Admin Panel – Sessions</title>
<style>
body { font-family: system-ui, Arial; background:#0f1115; color:#e6e6e6; margin:0; padding:20px; }
.container { max-width:800px; margin:0 auto; }
h1 { color:#5eead4; }
.card { background:#1a1d24; padding:20px; border-radius:12px; margin-bottom:20px; }
input, button { width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; margin-top:8px; box-sizing:border-box; }
button { background:#14b8a6; color:#000; font-weight:bold; cursor:pointer; }
.account { background:#222; padding:10px; border-radius:8px; margin:8px 0; display:flex; justify-content:space-between; align-items:center; }
.delete { background:#dc2626; color:#fff; padding:6px 12px; border-radius:6px; border:none; cursor:pointer; width:auto; }
.back { color:#5eead4; text-decoration:none; }
#log { background:#111; padding:15px; border-radius:8px; height:150px; overflow:auto; font-family:monospace; }
.success { color:#4ade80; } .error { color:#f87171; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← Zurück</a>
  <h1>Admin Panel – Sessions</h1>

  <div class="card">
    <h3>Neuen Account hinzufügen</h3>
    <input id="phone" placeholder="+491701234567">
    <button onclick="startLogin()">Code anfordern</button>
    <div id="codeArea" style="display:none; margin-top:10px;">
      <input id="code" placeholder="Code aus Telegram">
      <input id="password" placeholder="2FA Passwort (falls vorhanden)">
      <button onclick="finishLogin()">Einloggen</button>
    </div>
  </div>

  <div class="card">
    <h3>Vorhandene Sessions</h3>
    <div id="accountList"></div>
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
    container.innerHTML = '<p>Keine Sessions vorhanden.</p>';
    return;
  }
  container.innerHTML = sessions.map(s => `
    <div class="account">
      <span>${s}</span>
      <button class="delete" onclick="deleteSession('${s}')">Löschen</button>
    </div>
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
    log('Code gesendet.', 'success');
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

async function deleteSession(name) {
  if (!confirm('Session wirklich löschen?')) return;
  const res = await fetch('/session/delete', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  });
  const data = await res.json();
  if (data.ok) {
    log('Gelöscht: ' + name, 'success');
    loadAccounts();
  } else {
    log(data.error || 'Fehler', 'error');
  }
}

loadAccounts();
</script>
</body>
</html>
"""

SENDER_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Sender</title>
<style>
body { font-family: system-ui, Arial; background:#0f1115; color:#e6e6e6; margin:0; padding:20px; }
.container { max-width:800px; margin:0 auto; }
h1 { color:#5eead4; }
.card { background:#1a1d24; padding:20px; border-radius:12px; margin-bottom:20px; }
label { display:block; margin:12px 0 6px; font-weight:600; }
input, textarea, button { width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; box-sizing:border-box; }
button { background:#14b8a6; color:#000; font-weight:bold; cursor:pointer; margin-top:10px; }
.accounts { display:flex; flex-wrap:wrap; gap:10px; }
.account-item { background:#222; padding:8px 14px; border-radius:20px; }
#log { background:#111; padding:15px; border-radius:8px; height:200px; overflow:auto; font-family:monospace; }
.success { color:#4ade80; } .error { color:#f87171; }
.back { color:#5eead4; text-decoration:none; }
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← Zurück</a>
  <h1>Sender</h1>
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
    container.innerHTML = '<p>Keine Accounts vorhanden.</p>';
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
async def root(request: Request):
    if not check_auth(request):
        return RedirectResponse("/login")
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if check_auth(request):
        return RedirectResponse("/")
    html = LOGIN_HTML.replace("ERROR_PLACEHOLDER", f'<div class="error">{error}</div>' if error else "")
    return HTMLResponse(html)

@app.post("/login")
async def login(password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        token = secrets.token_urlsafe(32)
        sessions_tokens[token] = True
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("auth_token", token, httponly=True, max_age=86400*7)
        return response
    return RedirectResponse("/login?error=Falsches Passwort", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("auth_token")
    if token in sessions_tokens:
        sessions_tokens.pop(token, None)
    response = RedirectResponse("/login")
    response.delete_cookie("auth_token")
    return response

@app.get(f"/{ADMIN_SECRET_PATH}", response_class=HTMLResponse)
async def admin(request: Request):
    if not check_auth(request):
        return RedirectResponse("/login")
    return HTMLResponse(ADMIN_HTML)

@app.get("/sender", response_class=HTMLResponse)
async def sender(request: Request):
    if not check_auth(request):
        return RedirectResponse("/login")
    return HTMLResponse(SENDER_HTML)

@app.get("/sessions")
async def sessions(request: Request):
    if not check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return get_sessions()

@app.post("/session/delete")
async def delete_session(request: Request):
    if not check_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    data = await request.json()
    name = data.get("name", "")
    path = SESSIONS_DIR / f"{name}.session"
    if path.exists():
        path.unlink()
        return {"ok": True}
    return {"ok": False, "error": "Nicht gefunden"}

@app.post("/login/start")
async def login_start(request: Request):
    if not check_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
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
    if not check_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
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
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
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
    print(f"Passwort: {ADMIN_PASSWORD}")
    print(f"Admin URL: /{ADMIN_SECRET_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
