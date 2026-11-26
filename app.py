import asyncio
import os
import tempfile
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from dotenv import load_dotenv

load_dotenv()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

app = FastAPI(title="Telegram Multi Sender")

SESSIONS_DIR = Path(".")

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
.card { background:#1a1d24; padding:20px; border-radius:12px; margin-bottom:20px; box-shadow:0 4px 12px rgba(0,0,0,.4); }
label { display:block; margin:12px 0 6px; font-weight:600; }
input, textarea, button, select { width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; font-size:15px; box-sizing:border-box; }
button { background:#14b8a6; color:#000; font-weight:bold; cursor:pointer; margin-top:16px; }
button:hover { background:#0d9488; }
.accounts { display:flex; flex-wrap:wrap; gap:10px; }
.account-item { background:#222; padding:8px 14px; border-radius:20px; cursor:pointer; }
.account-item input { width:auto; margin-right:8px; }
#log { background:#111; padding:15px; border-radius:8px; height:280px; overflow:auto; font-family:monospace; white-space:pre-wrap; }
.success { color:#4ade80; }
.error { color:#f87171; }
.info { color:#60a5fa; }
</style>
</head>
<body>
<div class="container">
  <h1>Telegram Multi Video/File Sender</h1>
  
  <div class="card">
    <form id="sendForm">
      <label>Accounts auswählen</label>
      <div class="accounts" id="accountList"></div>
      
      <label>Gruppen-Link oder @username</label>
      <input type="text" name="group" placeholder="https://t.me/gruppe oder @gruppe" required>
      
      <label>Datei (Video, Bild, Dokument) – optional</label>
      <input type="file" name="file" accept="image/*,video/*,.pdf,.zip,.mp4,.mov">
      
      <label>Caption / Text (optional)</label>
      <textarea name="caption" rows="3" placeholder="Text unter dem Video..."></textarea>
      
      <label>Delay zwischen Accounts (Sekunden)</label>
      <input type="number" name="delay" value="8" min="3" max="60">
      
      <button type="submit">Jetzt senden</button>
    </form>
  </div>
  
  <div class="card">
    <h3>Log</h3>
    <div id="log">Bereit...</div>
  </div>
</div>

<script>
async function loadAccounts() {
  const res = await fetch('/sessions');
  const sessions = await res.json();
  const container = document.getElementById('accountList');
  if (sessions.length === 0) {
    container.innerHTML = '<p>Keine .session Dateien gefunden. Lege sie in denselben Ordner wie app.py.</p>';
    return;
  }
  container.innerHTML = sessions.map(s => `
    <label class="account-item">
      <input type="checkbox" name="accounts" value="${s}" checked> ${s}
    </label>
  `).join('');
}

function log(msg, type = 'info') {
  const el = document.getElementById('log');
  el.innerHTML += `<div class="${type}">${msg}</div>`;
  el.scrollTop = el.scrollHeight;
}

document.getElementById('sendForm').onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = new FormData(form);
  
  const checked = [...document.querySelectorAll('input[name="accounts"]:checked')].map(i => i.value);
  if (checked.length === 0) return alert('Bitte mindestens einen Account auswählen');
  
  data.delete('accounts');
  checked.forEach(a => data.append('accounts', a));
  
  log('Starte Senden...', 'info');
  const btn = form.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Sende...';
  
  try {
    const res = await fetch('/send', { method: 'POST', body: data });
    const result = await res.json();
    result.results.forEach(r => {
      log(r.message, r.ok ? 'success' : 'error');
    });
  } catch (err) {
    log('Fehler: ' + err, 'error');
  }
  
  btn.disabled = false;
  btn.textContent = 'Jetzt senden';
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

@app.post("/send")
async def send(
    request: Request,
    group: str = Form(...),
    caption: str = Form(""),
    delay: int = Form(8),
    file: UploadFile = File(None)
):
    form = await request.form()
    accounts = form.getlist("accounts")
    
    if not accounts:
        return JSONResponse({"results": [{"ok": False, "message": "Keine Accounts ausgewählt"}]})
    
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
            
        except FloodWaitError as e:
            results.append({"ok": False, "message": f"[{session_name}] FloodWait {e.seconds}s"})
            await asyncio.sleep(e.seconds)
        except Exception as e:
            results.append({"ok": False, "message": f"[{session_name}] Fehler: {str(e)[:120]}"})
            try:
                await client.disconnect()
            except:
                pass
    
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
    
    return {"results": results}

if __name__ == "__main__":
    print("Starte auf http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
