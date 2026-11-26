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
body { font-family: system-ui, -apple-system, sans-serif; background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); min-height:100vh; display:flex; align-items:center; justify-content:center; color:#fff; padding:20px; }
.box { background: rgba(255,255,255,0.08); backdrop-filter: blur(12px); border:1px solid rgba(255,255,255,0.15); border-radius:28px; padding:48px 36px; width:100%; max-width:400px; text-align:center; box-shadow:0 30px 80px rgba(0,0,0,0.5); }
h1 { font-size:32px; margin-bottom:8px; background: linear-gradient(90deg, #00f5ff, #ff6bcb); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
p { color:#aaa; margin-bottom:32px; }
input { width:100%; padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:#fff; font-size:16px; margin:10px 0; }
button { width:100%; padding:16px; background: linear-gradient(90deg, #00f5ff, #ff6bcb); border:none; border-radius:16px; color:#000; font-weight:700; font-size:16px; margin-top:12px; cursor:pointer; }
.error { color:#ff5555; margin-top:12px; }
</style>
</head>
<body>
<div class="box">
  <h1>⚡ Telegram</h1>
  <p>Admin Dashboard</p>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="Passwort" required>
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
body { font-family: system-ui, -apple-system, sans-serif; background:#0a0a12; color:#eee; min-height:100vh; }
.header { background: linear-gradient(90deg, #1a1a2e, #16213e); padding:16px 20px; display:flex; justify-content:space-between; align-items:center; position:sticky; top:0; z-index:100; }
.header h1 { font-size:20px; background: linear-gradient(90deg, #00f5ff, #ff6bcb); -webkit-background-clip:text; -webkit-text-fill-color:transparent; font-weight:800; }
.logout { background:#ef4444; color:#fff; padding:8px 14px; border-radius:12px; text-decoration:none; font-weight:600; font-size:13px; }
.stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; padding:16px; }
.stat { background: linear-gradient(145deg, #1e1e2e, #252536); border-radius:16px; padding:14px; text-align:center; }
.stat .num { font-size:22px; font-weight:800; background: linear-gradient(90deg, #00f5ff, #ff6bcb); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.stat .label { font-size:11px; color:#888; margin-top:4px; }
.container { max-width:520px; margin:0 auto; padding:0 16px 30px; }
.section { margin-bottom:20px; }
.section h2 { font-size:14px; color:#888; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.action { background: linear-gradient(145deg, #1a1a28, #222230); border-radius:16px; padding:18px; text-align:center; cursor:pointer; border:1px solid rgba(255,255,255,0.06); transition:transform 0.15s; }
.action:hover { transform:translateY(-2px); }
.action .icon { font-size:28px; margin-bottom:6px; }
.action .title { font-weight:700; font-size:14px; }
.action .sub { font-size:11px; color:#888; margin-top:2px; }
.blue { background: linear-gradient(145deg, #1e3a5f, #2563eb); }
.purple { background: linear-gradient(145deg, #4c1d95, #7c3aed); }
.green { background: linear-gradient(145deg, #065f46, #10b981); }
.orange { background: linear-gradient(145deg, #7c2d12, #f97316); }
.card { background:#161622; border-radius:16px; padding:16px; margin-bottom:12px; border:1px solid #222; }
input, textarea { width:100%; padding:12px; border-radius:12px; border:1px solid #2a2a3a; background:#0e0e16; color:#fff; font-size:14px; margin:6px 0; }
button { width:100%; padding:12px; background: linear-gradient(90deg, #00f5ff, #ff6bcb); color:#000; border:none; border-radius:12px; font-weight:700; margin-top:8px; cursor:pointer; }
.secondary { background:#333; color:#fff; }
.accounts { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
.chip { background:#252536; padding:6px 12px; border-radius:20px; font-size:13px; display:flex; align-items:center; gap:6px; }
.chip input { width:auto; margin:0; }
.session-item { background:#1e1e2e; padding:10px 12px; border-radius:10px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; }
.delete { background:#ef4444; color:#fff; border:none; padding:4px 10px; border-radius:8px; font-size:12px; width:auto; }
#log { background:#0e0e16; border-radius:10px; padding:12px; height:120px; overflow-y:auto; font-family:monospace; font-size:12px; }
.success { color:#4ade80; }
.error { color:#f87171; }
.info { color:#60a5fa; }
.row { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
@media (max-width:400px) { .grid, .row, .stats { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ Telegram</h1>
  <a href="/logout" class="logout">Logout</a>
</div>

<div class="stats">
  <div class="stat">
    <div class="num" id="sessionCount">0</div>
    <div class="label">Sessions</div>
  </div>
  <div class="stat">
    <div class="num">✓</div>
    <div class="label">Verifiziert</div>
  </div>
  <div class="stat">
    <div class="num">Online</div>
    <div class="label">Status</div>
  </div>
</div>

<div class="container">
  <div class="section">
    <h2>Schnellzugriff</h2>
    <div class="grid">
      <div class="action blue" onclick="showSection('sessions')">
        <div class="icon">📱</div>
        <div class="title">Sessions</div>
        <div class="sub">Accounts verwalten</div>
      </div>
      <div class="action purple" onclick="showSection('join')">
        <div class="icon">🔗</div>
        <div class="title">Joinen</div>
        <div class="sub">In Gruppen beitreten</div>
      </div>
      <div class="action green" onclick="showSection('send')">
        <div class="icon">📤</div>
        <div class="title">Senden</div>
        <div class="sub">Nachrichten schicken</div>
      </div>
      <div class="action orange" onclick="showSection('log')">
        <div class="icon">📋</div>
        <div class="title">Log</div>
        <div class="sub">Aktivität ansehen</div>
      </div>
    </div>
  </div>

  <div id="sessions" class="section" style="display:none;">
    <h2>Sessions</h2>
    <div class="card">
      <form id="uploadForm">
        <input type="file" id="sessionFile" accept=".session">
        <button type="submit">Session hochladen</button>
      </form>
    </div>
    <div class="card">
      <input id="phone" placeholder="+49 170 1234567">
      <button onclick="startLogin()">Code anfordern</button>
      <div id="codeArea" style="display:none;">
        <input id="code" placeholder="Code">
        <input id="password" placeholder="2FA (optional)">
        <button onclick="finishLogin()">Einloggen</button>
      </div>
    </div>
    <div class="card">
      <div id="sessionList"></div>
    </div>
  </div>

  <div id="join" class="section" style="display:none;">
    <h2>Joinen</h2>
    <div class="card">
      <label>Accounts</label>
      <div class="accounts" id="joinAccountSelect"></div>
      <input id="joinLink" placeholder="https://t.me/gruppe oder +invite">
      <button onclick="joinGroup()">Joinen</button>
    </div>
  </div>

  <div id="send" class="section" style="display:none;">
    <h2>Senden</h2>
    <div class="card">
      <form id="sendForm">
        <label>Accounts</label>
        <div class="accounts" id="accountSelect"></div>
        <button type="button" class="secondary" onclick="loadGroups()">Gruppen laden</button>
        <div id="groupList" style="max-height:180px; overflow-y:auto; margin:8px 0;"></div>
        <input name="group" id="manualGroup" placeholder="Oder manuell: @gruppe / Link">
        <input type="file" name="file">
        <textarea name="caption" placeholder="Nachricht..."></textarea>
        <div class="row">
          <div>
            <label>Wie oft</label>
            <input type="number" name="rounds" value="1" min="1">
          </div>
          <div>
            <label>Delay Accounts (s)</label>
            <input type="number" name="delay" value="8" min="1">
          </div>
        </div>
        <div class="row">
          <div>
            <label>Delay Runden (s)</label>
            <input type="number" name="round_delay" value="30" min="5">
          </div>
          <div>
            <label>Delay Nachrichten (s)</label>
            <input type="number" name="msg_delay" value="2" min="1">
          </div>
        </div>
        <button type="submit">Senden starten</button>
      </form>
    </div>
  </div>

  <div id="log" class="section" style="display:none;">
    <h2>Log</h2>
    <div class="card">
      <div id="log">Bereit...</div>
    </div>
  </div>
</div>

<script>
function showSection(id) {
  document.querySelectorAll('.section').forEach(s => {
    if (s.id) s.style.display = 'none';
  });
  document.getElementById(id).style.display = 'block';
}

async function loadSessions() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  document.getElementById('sessionCount').textContent = sessions.length;
  const list = document.getElementById('sessionList');
  const select = document.getElementById('accountSelect');
  const joinSelect = document.getElementById('joinAccountSelect');
  if (!sessions.length) {
    list.innerHTML = '<p style="color:#666;">Keine Sessions</p>';
    select.innerHTML = '<p style="color:#666;">Keine</p>';
    joinSelect.innerHTML = '<p style="color:#666;">Keine</p>';
    return;
  }
  list.innerHTML = sessions.map(s => `
    <div class="session-item">
      <span>${s}</span>
      <button class="delete" onclick="deleteSession('${s}')">Löschen</button>
    </div>
  `).join('');
  const chips = sessions.map(s => `<label class="chip"><input type="checkbox" name="accounts" value="${s}" checked> ${s}</label>`).join('');
  select.innerHTML = chips;
  joinSelect.innerHTML = sessions.map(s => `<label class="chip"><input type="checkbox" name="joinAccounts" value="${s}" checked> ${s}</label>`).join('');
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
  log('Joine...', 'info');
  const res = await fetch('/join', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({link, accounts}) });
  const data = await res.json();
  data.results.forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}

async function loadGroups() {
  const checked = [...document.querySelectorAll('input[name="accounts"]:checked')].map(i => i.value);
  if (!checked.length) return alert('Account auswählen');
  log('Lade Gruppen...', 'info');
  const res = await fetch('/groups', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts: checked}) });
  const data = await res.json();
  const list = document.getElementById('groupList');
  if (!data.groups || !data.groups.length) {
    list.innerHTML = '<p style="color:#666;">Keine Gruppen</p>';
    return;
  }
  list.innerHTML = data.groups.map(g => `
    <label class="chip" style="display:flex; width:100%; margin-bottom:4px;">
      <input type="checkbox" name="groups" value="${g.id}"> ${g.title}
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
  if (!groups.length && !manual) return alert('Gruppe auswählen');
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
async def send(
    request: Request,
    caption: str = Form(""),
    delay: int = Form(8),
    rounds: int = Form(1),
    round_delay: int = Form(30),
    msg_delay: int = Form(2),
    file: UploadFile = File(None)
):
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
    for r in range(rounds):
        if rounds > 1:
            results.append({"ok": True, "message": f"--- Runde {r+1}/{rounds} ---"})
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
                        await asyncio.sleep(msg_delay)
                    except Exception as e:
                        results.append({"ok": False, "message": f"[{name}] → {target}: {str(e)[:60]}"})
                await client.disconnect()
                await asyncio.sleep(delay)
            except Exception as e:
                results.append({"ok": False, "message": f"[{session_name}] {str(e)[:80]}"})
        if r < rounds - 1:
            await asyncio.sleep(round_delay)
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return {"results": results}

if __name__ == "__main__":
    print("Starte auf http://0.0.0.0:8000")
    print(f"Passwort: {ADMIN_PASSWORD}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
