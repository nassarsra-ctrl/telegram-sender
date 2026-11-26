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

app = FastAPI(title="Telegram Sender")

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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); min-height:100vh; display:flex; align-items:center; justify-content:center; color:#fff; }
.login-box { background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); border:1px solid rgba(255,255,255,0.1); padding:48px 40px; border-radius:24px; width:100%; max-width:400px; text-align:center; box-shadow:0 20px 60px rgba(0,0,0,0.4); }
h1 { font-size:32px; margin-bottom:8px; background: linear-gradient(90deg, #00d4ff, #7b2cbf); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.subtitle { color:#aaa; margin-bottom:32px; font-size:15px; }
input { width:100%; padding:14px 16px; margin:12px 0; border-radius:12px; border:1px solid rgba(255,255,255,0.15); background:rgba(0,0,0,0.3); color:#fff; font-size:16px; outline:none; transition:all 0.3s; }
input:focus { border-color:#00d4ff; box-shadow:0 0 0 3px rgba(0,212,255,0.2); }
button { width:100%; padding:14px; margin-top:8px; background: linear-gradient(90deg, #00d4ff, #7b2cbf); border:none; border-radius:12px; color:#fff; font-size:16px; font-weight:600; cursor:pointer; transition:transform 0.2s, box-shadow 0.2s; }
button:hover { transform:translateY(-2px); box-shadow:0 10px 25px rgba(0,212,255,0.3); }
.error { color:#ff6b6b; margin-top:16px; font-size:14px; }
</style>
</head>
<body>
<div class="login-box">
  <h1>Telegram Sender</h1>
  <div class="subtitle">Admin Dashboard</div>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="Passwort eingeben" required autofocus>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Dashboard</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background:#0a0a0f; color:#e8e8e8; min-height:100vh; }
.header { background: linear-gradient(90deg, #1a1a2e, #16213e); padding:20px 40px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.08); }
.header h1 { font-size:24px; background: linear-gradient(90deg, #00d4ff, #a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.logout { background:#ef4444; color:#fff; padding:10px 20px; border-radius:10px; text-decoration:none; font-weight:600; transition:background 0.2s; }
.logout:hover { background:#dc2626; }
.container { max-width:1100px; margin:0 auto; padding:30px 20px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
@media (max-width:800px) { .grid { grid-template-columns:1fr; } }
.card { background:#12121a; border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:24px; }
.card h2 { font-size:18px; margin-bottom:16px; color:#00d4ff; display:flex; align-items:center; gap:8px; }
label { display:block; margin:12px 0 6px; font-weight:500; color:#ccc; font-size:14px; }
input, textarea, select { width:100%; padding:12px 14px; border-radius:10px; border:1px solid rgba(255,255,255,0.1); background:#1a1a24; color:#fff; font-size:15px; outline:none; transition:border 0.2s; }
input:focus, textarea:focus { border-color:#00d4ff; }
textarea { resize:vertical; min-height:80px; }
button { background: linear-gradient(90deg, #00d4ff, #7b2cbf); color:#fff; border:none; padding:12px 20px; border-radius:10px; font-weight:600; cursor:pointer; transition:transform 0.2s, opacity 0.2s; width:100%; margin-top:12px; }
button:hover { transform:translateY(-1px); }
button:disabled { opacity:0.6; cursor:not-allowed; }
.accounts { display:flex; flex-wrap:wrap; gap:10px; margin-top:8px; }
.account-chip { background:#1e1e2e; border:1px solid rgba(255,255,255,0.1); padding:8px 14px; border-radius:20px; display:flex; align-items:center; gap:8px; font-size:14px; }
.account-chip input { width:auto; margin:0; }
.account-list { max-height:200px; overflow-y:auto; }
.session-item { background:#1a1a24; padding:12px 16px; border-radius:10px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.delete-btn { background:#ef4444; color:#fff; border:none; padding:6px 12px; border-radius:8px; cursor:pointer; font-size:13px; width:auto; }
#log { background:#0d0d12; border-radius:10px; padding:16px; height:180px; overflow-y:auto; font-family:monospace; font-size:13px; line-height:1.5; }
.success { color:#4ade80; }
.error { color:#f87171; }
.info { color:#60a5fa; }
.verified { background: linear-gradient(90deg, #065f46, #047857); color:#6ee7b7; padding:6px 14px; border-radius:20px; font-size:13px; font-weight:600; }
</style>
</head>
<body>
<div class="header">
  <h1>Telegram Admin Dashboard</h1>
  <div style="display:flex; align-items:center; gap:16px;">
    <span class="verified">Verifiziert ✓</span>
    <a href="/logout" class="logout">Logout</a>
  </div>
</div>

<div class="container">
  <div class="grid">
    <!-- Account hinzufügen -->
    <div class="card">
      <h2>➕ Account hinzufügen</h2>
      <input id="phone" placeholder="+49 170 1234567">
      <button onclick="startLogin()">Code anfordern</button>
      <div id="codeArea" style="display:none; margin-top:12px;">
        <input id="code" placeholder="Code aus Telegram">
        <input id="password" placeholder="2FA Passwort (optional)" style="margin-top:8px;">
        <button onclick="finishLogin()">Einloggen</button>
      </div>
    </div>

    <!-- Sessions -->
    <div class="card">
      <h2>📱 Sessions</h2>
      <div id="sessionList" class="account-list"></div>
    </div>

    <!-- Senden -->
    <div class="card" style="grid-column:1 / -1;">
      <h2>📤 Nachricht senden</h2>
      <form id="sendForm">
        <label>Accounts auswählen</label>
        <div class="accounts" id="accountSelect"></div>
        
        <label>Gruppen-Link oder @username</label>
        <input name="group" placeholder="https://t.me/gruppe oder @gruppe" required>
        
        <label>Datei (optional)</label>
        <input type="file" name="file">
        
        <label>Text / Caption</label>
        <textarea name="caption" placeholder="Nachricht..."></textarea>
        
        <label>Delay zwischen Accounts (Sekunden)</label>
        <input type="number" name="delay" value="8" min="3" max="120">
        
        <button type="submit">Jetzt senden</button>
      </form>
    </div>

    <!-- Log -->
    <div class="card" style="grid-column:1 / -1;">
      <h2>📋 Log</h2>
      <div id="log">Bereit...</div>
    </div>
  </div>
</div>

<script>
async function loadSessions() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  
  const list = document.getElementById('sessionList');
  const select = document.getElementById('accountSelect');
  
  if (!sessions.length) {
    list.innerHTML = '<p style="color:#888;">Keine Sessions vorhanden</p>';
    select.innerHTML = '<p style="color:#888;">Keine Accounts</p>';
    return;
  }
  
  list.innerHTML = sessions.map(s => `
    <div class="session-item">
      <span>${s}</span>
      <button class="delete-btn" onclick="deleteSession('${s}')">Löschen</button>
    </div>
  `).join('');
  
  select.innerHTML = sessions.map(s => `
    <label class="account-chip">
      <input type="checkbox" name="accounts" value="${s}" checked>
      ${s}
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
    log('Code gesendet an ' + phone, 'success');
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
    log('Account hinzugefügt: ' + (data.name || phone), 'success');
    document.getElementById('codeArea').style.display = 'none';
    document.getElementById('phone').value = '';
    loadSessions();
  } else {
    log(data.error || 'Fehler', 'error');
  }
}

async function deleteSession(name) {
  if (!confirm('Session "' + name + '" wirklich löschen?')) return;
  const res = await fetch('/session/delete', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  });
  const data = await res.json();
  if (data.ok) {
    log('Session gelöscht: ' + name, 'success');
    loadSessions();
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
  
  log('Starte Senden an ' + checked.length + ' Account(s)...', 'info');
  const btn = form.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Sende...';
  
  try {
    const res = await fetch('/send', {method:'POST', body:data});
    const result = await res.json();
    result.results.forEach(r => log(r.message, r.ok ? 'success' : 'error'));
  } catch(err) {
    log('Fehler: ' + err, 'error');
  }
  
  btn.disabled = false;
  btn.textContent = 'Jetzt senden';
};

loadSessions();
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
