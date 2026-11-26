import asyncio
import os
import tempfile
import secrets
import shutil
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
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
body { font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background:#05050a; min-height:100vh; display:flex; align-items:center; justify-content:center; color:#fff; padding:20px; }
.login-box { background: linear-gradient(160deg, #111118 0%, #1a1a28 100%); border:1px solid rgba(255,255,255,0.08); padding:48px 36px; border-radius:32px; width:100%; max-width:420px; text-align:center; box-shadow:0 40px 100px rgba(0,0,0,0.7); }
.logo { font-size:42px; margin-bottom:8px; }
h1 { font-size:28px; margin-bottom:4px; background: linear-gradient(90deg, #00f5ff, #b24bf3); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-weight:800; letter-spacing:-0.5px; }
.subtitle { color:#777; margin-bottom:36px; font-size:15px; }
input { width:100%; padding:16px 18px; margin:10px 0; border-radius:16px; border:1px solid rgba(255,255,255,0.1); background:#0a0a10; color:#fff; font-size:16px; outline:none; transition:all 0.2s; }
input:focus { border-color:#00f5ff; box-shadow:0 0 0 4px rgba(0,245,255,0.15); }
button { width:100%; padding:16px; margin-top:12px; background: linear-gradient(90deg, #00f5ff, #b24bf3); border:none; border-radius:16px; color:#000; font-size:16px; font-weight:700; cursor:pointer; transition:transform 0.15s; }
button:hover { transform:translateY(-1px); }
.error { color:#ff5555; margin-top:16px; font-size:14px; }
</style>
</head>
<body>
<div class="login-box">
  <div class="logo">⚡</div>
  <h1>Telegram</h1>
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
<title>Dashboard</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; background:#05050a; color:#eee; min-height:100vh; }
.header { background: linear-gradient(90deg, #0c0c14, #141420); padding:16px 20px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.06); position:sticky; top:0; z-index:100; backdrop-filter:blur(12px); }
.header h1 { font-size:20px; background: linear-gradient(90deg, #00f5ff, #b24bf3); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-weight:800; }
.header-right { display:flex; align-items:center; gap:10px; }
.verified { background: linear-gradient(90deg, #065f46, #047857); color:#6ee7b7; padding:6px 12px; border-radius:20px; font-size:12px; font-weight:700; }
.logout { background:#ef4444; color:#fff; padding:8px 14px; border-radius:12px; text-decoration:none; font-weight:700; font-size:13px; }
.container { max-width:900px; margin:0 auto; padding:16px; }
.tabs { display:flex; gap:8px; margin-bottom:16px; overflow-x:auto; padding-bottom:4px; }
.tab { background:#12121c; border:1px solid rgba(255,255,255,0.08); color:#aaa; padding:10px 18px; border-radius:14px; cursor:pointer; font-weight:600; font-size:14px; white-space:nowrap; transition:all 0.2s; }
.tab.active { background: linear-gradient(90deg, #00f5ff, #b24bf3); color:#000; border-color:transparent; }
.panel { display:none; }
.panel.active { display:block; }
.card { background: linear-gradient(160deg, #101018, #161620); border:1px solid rgba(255,255,255,0.06); border-radius:20px; padding:20px; margin-bottom:14px; }
.card h2 { font-size:17px; margin-bottom:14px; color:#00f5ff; font-weight:700; }
label { display:block; margin:12px 0 6px; font-weight:600; color:#ccc; font-size:13px; }
input, textarea { width:100%; padding:14px; border-radius:14px; border:1px solid rgba(255,255,255,0.08); background:#0a0a10; color:#fff; font-size:15px; outline:none; }
input:focus, textarea:focus { border-color:#00f5ff; }
textarea { resize:vertical; min-height:70px; }
button { background: linear-gradient(90deg, #00f5ff, #b24bf3); color:#000; border:none; padding:14px; border-radius:14px; font-weight:700; cursor:pointer; width:100%; margin-top:10px; font-size:15px; }
button:disabled { opacity:0.5; }
.secondary { background:#1e1e2e; color:#fff; }
.accounts { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.account-chip { background:#1a1a28; border:1px solid rgba(255,255,255,0.08); padding:10px 14px; border-radius:24px; display:flex; align-items:center; gap:8px; font-size:14px; }
.account-chip input { width:auto; margin:0; }
.session-item { background:#14141e; padding:12px 14px; border-radius:14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.delete-btn { background:#ef4444; color:#fff; border:none; padding:6px 12px; border-radius:10px; cursor:pointer; font-size:13px; width:auto; margin:0; }
.groups { max-height:260px; overflow-y:auto; margin-top:8px; }
.group-item { background:#14141e; padding:12px 14px; border-radius:14px; margin-bottom:6px; display:flex; align-items:center; gap:10px; }
.group-item input { width:auto; }
#log { background:#0a0a10; border-radius:14px; padding:14px; height:150px; overflow-y:auto; font-family:monospace; font-size:13px; }
.success { color:#4ade80; }
.error { color:#f87171; }
.info { color:#60a5fa; }
.file-upload { border:2px dashed rgba(255,255,255,0.12); border-radius:16px; padding:28px; text-align:center; }
.file-upload input { display:none; }
.file-upload label { color:#00f5ff; cursor:pointer; font-weight:700; }
@media (max-width:480px) {
  .verified { display:none; }
  .header h1 { font-size:18px; }
  .tab { padding:8px 14px; font-size:13px; }
}
</style>
</head>
<body>
<div class="header">
  <h1>⚡ Telegram</h1>
  <div class="header-right">
    <span class="verified">Verifiziert ✓</span>
    <a href="/logout" class="logout">Logout</a>
  </div>
</div>

<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('sessions')">Sessions</div>
    <div class="tab" onclick="switchTab('join')">Joinen</div>
    <div class="tab" onclick="switchTab('send')">Senden</div>
    <div class="tab" onclick="switchTab('log')">Log</div>
  </div>

  <div id="sessions" class="panel active">
    <div class="card">
      <h2>📁 Session hochladen</h2>
      <form id="uploadForm">
        <div class="file-upload">
          <input type="file" id="sessionFile" accept=".session">
          <label for="sessionFile">.session Datei auswählen</label>
          <div id="fileName" style="margin-top:8px; color:#888; font-size:13px;"></div>
        </div>
        <button type="submit">Hochladen</button>
      </form>
    </div>
    <div class="card">
      <h2>➕ Account per Telefon</h2>
      <input id="phone" placeholder="+49 170 1234567">
      <button onclick="startLogin()">Code anfordern</button>
      <div id="codeArea" style="display:none; margin-top:12px;">
        <input id="code" placeholder="Code">
        <input id="password" placeholder="2FA (optional)" style="margin-top:8px;">
        <button onclick="finishLogin()">Einloggen</button>
      </div>
    </div>
    <div class="card">
      <h2>📱 Sessions</h2>
      <div id="sessionList"></div>
    </div>
  </div>

  <div id="join" class="panel">
    <div class="card">
      <h2>🔗 In Gruppe joinen</h2>
      <label>Accounts</label>
      <div class="accounts" id="joinAccountSelect"></div>
      <label>Gruppen-Link</label>
      <input id="joinLink" placeholder="https://t.me/gruppe oder https://t.me/+invite">
      <button onclick="joinGroup()">Joinen</button>
    </div>
  </div>

  <div id="send" class="panel">
    <div class="card">
      <h2>📤 Nachricht senden</h2>
      <form id="sendForm">
        <label>Accounts</label>
        <div class="accounts" id="accountSelect"></div>
        <button type="button" class="secondary" onclick="loadGroups()">Gruppen laden</button>
        <div class="groups" id="groupList"></div>
        <label>Oder manuell eingeben</label>
        <input name="group" id="manualGroup" placeholder="https://t.me/gruppe oder @gruppe">
        <label>Datei (optional)</label>
        <input type="file" name="file">
        <label>Text / Caption</label>
        <textarea name="caption" placeholder="Nachricht..."></textarea>
        <label>Delay (Sekunden)</label>
        <input type="number" name="delay" value="8" min="3">
        <button type="submit">Senden</button>
      </form>
    </div>
  </div>

  <div id="log" class="panel">
    <div class="card">
      <h2>📋 Log</h2>
      <div id="log">Bereit...</div>
    </div>
  </div>
</div>

<script>
function switchTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById(id).classList.add('active');
}

document.getElementById('sessionFile').onchange = function() {
  document.getElementById('fileName').textContent = this.files[0] ? this.files[0].name : '';
};

async function loadSessions() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  const list = document.getElementById('sessionList');
  const select = document.getElementById('accountSelect');
  const joinSelect = document.getElementById('joinAccountSelect');
  if (!sessions.length) {
    list.innerHTML = '<p style="color:#666;">Keine Sessions</p>';
    select.innerHTML = '<p style="color:#666;">Keine Accounts</p>';
    joinSelect.innerHTML = '<p style="color:#666;">Keine Accounts</p>';
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="session-item">
      <span>${s}</span>
      <button class="delete-btn" onclick="deleteSession('${s}')">Löschen</button>
    </div>
  `).join('');
  const chips = sessions.map(s => `
    <label class="account-chip">
      <input type="checkbox" name="accounts" value="${s}" checked> ${s}
    </label>
  `).join('');
  select.innerHTML = chips;
  joinSelect.innerHTML = sessions.map(s => `
    <label class="account-chip">
      <input type="checkbox" name="joinAccounts" value="${s}" checked> ${s}
    </label>
  `).join('');
}

function log(msg, type='info') {
  const el = document.getElementById('log');
  el.innerHTML += `<div class="${type}">${msg}</div>`;
  el.scrollTop = el.scrollHeight;
}

document.getElementById('uploadForm').onsubmit = async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('sessionFile');
  if (!fileInput.files[0]) return alert('Datei auswählen');
  const data = new FormData();
  data.append('file', fileInput.files[0]);
  log('Lade Session hoch...', 'info');
  try {
    const res = await fetch('/session/upload', { method:'POST', body:data });
    const result = await res.json();
    if (result.ok) {
      log('Hochgeladen: ' + result.name, 'success');
      fileInput.value = '';
      document.getElementById('fileName').textContent = '';
      loadSessions();
    } else log(result.error || 'Fehler', 'error');
  } catch(err) { log('Fehler: ' + err, 'error'); }
};

async function startLogin() {
  const phone = document.getElementById('phone').value.trim();
  if (!phone) return alert('Nummer eingeben');
  const res = await fetch('/login/start', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('codeArea').style.display = 'block';
    log('Code gesendet', 'success');
  } else log(data.error || 'Fehler', 'error');
}

async function finishLogin() {
  const phone = document.getElementById('phone').value.trim();
  const code = document.getElementById('code').value.trim();
  const password = document.getElementById('password').value.trim();
  const res = await fetch('/login/finish', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone, code, password}) });
  const data = await res.json();
  if (data.ok) {
    log('Account hinzugefügt: ' + (data.name || phone), 'success');
    document.getElementById('codeArea').style.display = 'none';
    document.getElementById('phone').value = '';
    loadSessions();
  } else log(data.error || 'Fehler', 'error');
}

async function deleteSession(name) {
  if (!confirm('Löschen?')) return;
  const res = await fetch('/session/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name}) });
  const data = await res.json();
  if (data.ok) { log('Gelöscht: ' + name, 'success'); loadSessions(); }
  else log(data.error || 'Fehler', 'error');
}

async function joinGroup() {
  const link = document.getElementById('joinLink').value.trim();
  const accounts = [...document.querySelectorAll('input[name="joinAccounts"]:checked')].map(i => i.value);
  if (!link) return alert('Link eingeben');
  if (!accounts.length) return alert('Account auswählen');
  log('Joine Gruppe...', 'info');
  const res = await fetch('/join', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({link, accounts}) });
  const data = await res.json();
  data.results.forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}

async function loadGroups() {
  const checked = [...document.querySelectorAll('input[name="accounts"]:checked')].map(i => i.value);
  if (!checked.length) return alert('Mindestens einen Account auswählen');
  log('Lade Gruppen...', 'info');
  const res = await fetch('/groups', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts: checked}) });
  const data = await res.json();
  const list = document.getElementById('groupList');
  if (!data.groups || !data.groups.length) {
    list.innerHTML = '<p style="color:#666;">Keine Gruppen gefunden</p>';
    return;
  }
  list.innerHTML = data.groups.map(g => `
    <label class="group-item">
      <input type="checkbox" name="groups" value="${g.id}">
      ${g.title}
    </label>
  `).join('');
  log(data.groups.length + ' Gruppen geladen', 'success');
}

document.getElementById('sendForm').onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = new FormData(form);
  const accounts = [...document.querySelectorAll('input[name="accounts"]:checked')].map(i => i.value);
  const groups = [...document.querySelectorAll('input[name="groups"]:checked')].map(i => i.value);
  const manual = document.getElementById('manualGroup').value.trim();
  if (!accounts.length) return alert('Account auswählen');
  if (!groups.length && !manual) return alert('Gruppe auswählen oder manuell eingeben');
  data.delete('accounts');
  data.delete('groups');
  accounts.forEach(a => data.append('accounts', a));
  groups.forEach(g => data.append('groups', g));
  if (manual) data.append('manual', manual);
  log('Sende...', 'info');
  const btn = form.querySelector('button[type=submit]');
  btn.disabled = true;
  try {
    const res = await fetch('/send', {method:'POST', body:data});
    const result = await res.json();
    result.results.forEach(r => log(r.message, r.ok ? 'success' : 'error'));
  } catch(err) { log('Fehler: ' + err, 'error'); }
  btn.disabled = false;
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

@app.post("/groups")
async def get_groups(request: Request):
    if not check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    accounts = data.get("accounts", [])
    groups = []
    seen = set()
    for session_name in accounts[:3]:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    if dialog.id not in seen:
                        seen.add(dialog.id)
                        groups.append({"id": dialog.id, "title": dialog.title or str(dialog.id)})
            await client.disconnect()
        except Exception:
            pass
    return {"groups": groups[:100]}

@app.post("/join")
async def join_group(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    data = await request.json()
    link = data.get("link", "").strip()
    accounts = data.get("accounts", [])
    results = []
    for session_name in accounts:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            me = await client.get_me()
            name = me.first_name or session_name
            if "/+" in link or "joinchat" in link:
                hash_part = link.split("/")[-1].replace("+", "")
                await client(ImportChatInviteRequest(hash_part))
            else:
                await client(JoinChannelRequest(link))
            results.append({"ok": True, "message": f"[{name}] erfolgreich gejoint"})
            await client.disconnect()
            await asyncio.sleep(2)
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:80]}"})
    return {"results": results}

@app.post("/session/upload")
async def upload_session(request: Request, file: UploadFile = File(...)):
    if not check_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    if not file.filename.endswith(".session"):
        return {"ok": False, "error": "Nur .session Dateien"}
    name = Path(file.filename).stem
    dest = SESSIONS_DIR / f"{name}.session"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True, "name": name}

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
            return {"ok": False, "error": "2FA nötig"}
        await client.sign_in(password=password)
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
    me = await client.get_me()
    await client.disconnect()
    login_clients.pop(phone, None)
    return {"ok": True, "name": me.first_name or phone}

@app.post("/send")
async def send(request: Request, caption: str = Form(""), delay: int = Form(8), file: UploadFile = File(None)):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    form = await request.form()
    accounts = form.getlist("accounts")
    groups = form.getlist("groups")
    manual = form.get("manual", "").strip()
    targets = groups + ([manual] if manual else [])
    if not accounts or not targets:
        return {"results": [{"ok": False, "message": "Keine Accounts oder Gruppen"}]}
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
            for target in targets:
                try:
                    if temp_path:
                        await client.send_file(int(target) if str(target).lstrip('-').isdigit() else target, temp_path, caption=caption or None)
                    elif caption:
                        await client.send_message(int(target) if str(target).lstrip('-').isdigit() else target, caption)
                    results.append({"ok": True, "message": f"[{name}] → {target} gesendet"})
                except Exception as e:
                    results.append({"ok": False, "message": f"[{name}] → {target}: {str(e)[:60]}"})
            await client.disconnect()
            await asyncio.sleep(delay)
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:80]}"})
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return {"results": results}

if __name__ == "__main__":
    print("Starte auf http://0.0.0.0:8000")
    print(f"Passwort: {ADMIN_PASSWORD}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
