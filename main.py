import os
import time
import sqlite3
import subprocess
import threading
import requests
from fastapi import FastAPI, UploadFile, File, Form, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

# المجلدات الأساسية
UPLOAD_DIR = "hosted_projects"
LOGS_DIR = "app_logs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# المتغيرات الخاصة في الذاكرة
running_processes = {}
process_files = {}
sessions = {}

# بيانات إشعارات التلجرام للأدمن (القيادة قوج)
ADMIN_TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_qoj_alert(message):
    try:
        if ADMIN_TELEGRAM_TOKEN != "YOUR_BOT_TOKEN_HERE":
            url = f"https://api.telegram.org/bot{ADMIN_TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": f"🚨 تنبيه للقيادة قوج:\n{message}"}, timeout=5)
    except Exception:
        pass

# --- 1. إدارة قاعدة البيانات ---
def get_db():
    conn = sqlite3.connect("platform.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            points INTEGER DEFAULT 100,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            filename TEXT,
            app_type TEXT,
            status TEXT DEFAULT 'stopped'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            points INTEGER,
            used INTEGER DEFAULT 0
        )
    ''')
    try:
        cursor.execute("INSERT INTO users (username, password, points, is_admin) VALUES ('admin', 'admin123', 9999, 1)")
        cursor.execute("INSERT INTO vouchers (code, points) VALUES ('QOJ2026', 200)")
    except sqlite3.IntegrityError:
        pass
    conn.commit()
    conn.close()

init_db()

# --- 2. محرك النقاط والخصم التلقائي ---
def auto_credits_engine():
    while True:
        time.sleep(3600)  # خصم كل ساعة
        conn = get_db()
        cursor = conn.cursor()
        for app_id, proc in list(running_processes.items()):
            cursor.execute("SELECT user_id FROM apps WHERE id = ?", (app_id,))
            app_data = cursor.fetchone()
            if app_data:
                user_id = app_data["user_id"]
                cursor.execute("SELECT points FROM users WHERE id = ?", (user_id,))
                user = cursor.fetchone()
                if user and user["points"] > 0:
                    cursor.execute("UPDATE users SET points = points - 1 WHERE id = ?", (user_id,))
                else:
                    proc.terminate()
                    del running_processes[app_id]
                    cursor.execute("UPDATE apps SET status = 'stopped' WHERE id = ?", (app_id,))
        cursor.execute("UPDATE users SET points = points + 10 WHERE is_admin = 0")
        conn.commit()
        conn.close()

threading.Thread(target=auto_credits_engine, daemon=True).start()

def get_current_user(session_id: str):
    if session_id and session_id in sessions:
        user_id = sessions[session_id]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    return None

# --- محرك تحديد أوامر التشغيل لجميع لغات البرمجة ---
def get_run_command(app_type, file_path):
    if app_type == "python":
        return ["python3", file_path]
    elif app_type == "node":
        return ["node", file_path]
    elif app_type == "php":
        return ["php", file_path]
    elif app_type == "go":
        return ["go", "run", file_path]
    elif app_type == "ruby":
        return ["ruby", file_path]
    elif app_type == "bash":
        return ["bash", file_path]
    elif app_type == "cpp":
        exe_path = file_path + ".out"
        subprocess.run(["g++", file_path, "-o", exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return [exe_path]
    elif app_type == "rust":
        exe_path = file_path + ".out"
        subprocess.run(["rustc", file_path, "-o", exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return [exe_path]
    elif app_type == "java":
        return ["java", file_path]
    elif app_type == "csharp":
        return ["dotnet", "run", "--project", file_path]
    else:
        return ["python3", file_path]
  # --- 3. صفحات تسجيل الدخول والتسجيل ---
@app.get("/login", response_class=HTMLResponse)
def login_page(msg: str = ""):
    return f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>القيادة قوج - تسجيل الدخول</title>
        <style>
            * {{ box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }}
            body {{ background: #0d0d11; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
            .login-card {{ background: #16161a; border: 1px solid #282830; padding: 40px; border-radius: 16px; width: 100%; max-width: 450px; text-align: center; box-shadow: 0 15px 35px rgba(0,0,0,0.6); }}
            .login-card h1 {{ font-size: 26px; margin-bottom: 5px; color: #00d2ff; }}
            .login-card p {{ color: #777; font-size: 14px; margin-bottom: 25px; }}
            .error-msg {{ background: #3a1317; color: #ff5252; padding: 12px; border-radius: 8px; margin-bottom: 15px; font-size: 14px; border: 1px solid #631d23; }}
            input {{ width: 100%; padding: 15px; margin: 8px 0; background: #202026; border: 1px solid #333340; color: #fff; font-size: 15px; border-radius: 10px; outline: none; }}
            button {{ width: 100%; padding: 15px; margin-top: 15px; background: #007bff; border: none; color: #fff; font-size: 17px; font-weight: bold; border-radius: 10px; cursor: pointer; transition: 0.3s; }}
            button:hover {{ background: #0056b3; }}
            .reg-link {{ display: inline-block; margin-top: 20px; color: #00d2ff; text-decoration: none; font-size: 14px; }}
            .footer-tag {{ margin-top: 30px; font-size: 12px; color: #777; border-top: 1px solid #222; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="login-card">
            <h1>🌐 القيادة قوج</h1>
            <p>منصة الاستضافة السحابية وخدمات تشغيل البوتات بكل اللغات</p>
            {f'<div class="error-msg">{msg}</div>' if msg else ''}
            <form action="/login" method="post">
                <input type="text" name="username" placeholder="اسم المستخدم" required>
                <input type="password" name="password" placeholder="كلمة السر" required>
                <button type="submit">تسجيل الدخول 🚀</button>
            </form>
            <a href="/register" class="reg-link">ليس لديك حساب في منصة القيادة قوج؟ اضغط هنا للتسجيل</a>
            <div class="footer-tag">جميع الحقوق محفوظة © القيادة قوج</div>
        </div>
    </body>
    </html>
    """

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    if user:
        session_id = f"sess_{user['id']}_{str(int(time.time()))}"
        sessions[session_id] = user["id"]
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_id", value=session_id)
        return response
    return RedirectResponse(url="/login?msg=بيانات الدخول غير صحيحة", status_code=303)

@app.get("/register", response_class=HTMLResponse)
def register_page(msg: str = ""):
    return f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>إنشاء حساب - القيادة قوج</title>
        <style>
            * {{ box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }}
            body {{ background: #0d0d11; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }}
            .card {{ background: #16161a; border: 1px solid #282830; padding: 40px; border-radius: 16px; width: 100%; max-width: 450px; text-align: center; }}
            h1 {{ font-size: 24px; color: #28a745; margin-bottom: 20px; }}
            input {{ width: 100%; padding: 15px; margin: 8px 0; background: #202026; border: 1px solid #333340; color: #fff; font-size: 15px; border-radius: 10px; outline: none; }}
            button {{ width: 100%; padding: 15px; margin-top: 15px; background: #28a745; border: none; color: #fff; font-size: 17px; font-weight: bold; border-radius: 10px; cursor: pointer; }}
            a {{ color: #00d2ff; text-decoration: none; display: inline-block; margin-top: 15px; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>إنشاء حساب جديد ✨</h1>
            {f'<div style="color:#ff5252; margin-bottom:15px;">{msg}</div>' if msg else ''}
            <form action="/register" method="post">
                <input type="text" name="username" placeholder="اختر اسم المستخدم" required>
                <input type="password" name="password" placeholder="اختر كلمة السر" required>
                <button type="submit">إنشاء الحساب الآن</button>
            </form>
            <a href="/login">لديك حساب بالفعل في القيادة قوج؟ تسجيل الدخول</a>
        </div>
    </body>
    </html>
    """

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, points) VALUES (?, ?, 100)", (username, password))
        conn.commit()
        conn.close()
        send_qoj_alert(f"👤 تسجيل مستخدم جديد في منصة القيادة قوج:\nاسم المستخدم: {username}")
        return RedirectResponse(url="/login?msg=تم إنشاء الحساب بنجاح!", status_code=303)
    except sqlite3.IntegrityError:
        conn.close()
        return RedirectResponse(url="/register?msg=اسم المستخدم مستخدم بالفعل", status_code=303)

@app.get("/logout")
def logout(session_id: str = Cookie(None)):
    if session_id and session_id in sessions:
        del sessions[session_id]
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_id")
    return response

# --- 4. الصفحة الرئيسية للموقع ---
@app.get("/", response_class=HTMLResponse)
def home(session_id: str = Cookie(None), msg: str = ""):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    
    if user["is_admin"] == 1:
        cursor.execute("SELECT apps.*, users.username FROM apps JOIN users ON apps.user_id = users.id")
    else:
        cursor.execute("SELECT * FROM apps WHERE user_id = ?", (user["id"],))
    apps = cursor.fetchall()
    
    users_list_html = ""
    vouchers_list_html = ""
    if user["is_admin"] == 1:
        cursor.execute("SELECT * FROM users")
        all_users = cursor.fetchall()
        for u in all_users:
            users_list_html += f"<tr><td>{u['id']}</td><td>{u['username']}</td><td>{u['points']} نقطة</td><td><a href='/admin/add_points/{u['id']}' style='color:#00d2ff; text-decoration:none;'>+50 نقطة</a> | <a href='/admin/delete_user/{u['id']}' style='color:#ff5252; text-decoration:none;'>حذف</a></td></tr>"
        
        cursor.execute("SELECT * FROM vouchers")
        all_vouchers = cursor.fetchall()
        for v in all_vouchers:
            status_v = "مستخدم 🔴" if v['used'] else "متاح 🟢"
            vouchers_list_html += f"<tr><td>{v['code']}</td><td>{v['points']} نقطة</td><td>{status_v}</td></tr>"

    conn.close()

    lang_badges = {
        "python": "🐍 Python", "node": "🟨 Node.js", "php": "🐘 PHP",
        "go": "🐹 Go", "ruby": "💎 Ruby", "cpp": "⚙️ C++",
        "rust": "🦀 Rust", "java": "☕ Java", "csharp": "🔷 C#", "bash": "🐚 Bash / Shell"
    }

    apps_html = ""
    for item in apps:
        badge = lang_badges.get(item["app_type"], "💻 " + item["app_type"])
        status_color = "#28a745" if item["id"] in running_processes else "#dc3545"
        status_text = "شغال 🟢" if item["id"] in running_processes else "متوقف 🔴"
        owner = f" | المالك: {item['username']}" if user["is_admin"] == 1 else ""

        apps_html += f"""
        <div style="border: 1px solid #282830; padding: 15px; margin-bottom: 12px; border-radius: 10px; background: #16161a;">
            <span style="background: #22222a; padding: 4px 10px; border-radius: 5px; font-size: 12px; color:#00d2ff;">{badge}</span>
            <h3 style="margin: 8px 0 5px 0; color: #fff;">{item['name']}</h3>
            <p style="color: #aaa; margin: 2px 0; font-size: 14px;">الملف: {item['filename']} {owner} | الحالة: <b style="color:{status_color};">{status_text}</b></p>
            <div style="margin-top: 10px;">
                <a href="/action/start/{item['id']}" style="color: #28a745; font-weight: bold; margin-left: 15px; text-decoration: none;">[ ▶ تشغيل ]</a>
                <a href="/action/stop/{item['id']}" style="color: #dc3545; font-weight: bold; margin-left: 15px; text-decoration: none;">[ ⏹ إيقاف ]</a>
                <a href="/logs/{item['id']}" target="_blank" style="color: #ff9800; font-weight: bold; margin-left: 15px; text-decoration: none;">[ 📜 السجل المباشر ]</a>
                <a href="/action/delete/{item['id']}" style="color: #ff5252; font-weight: bold; text-decoration: none;">[ 🗑️ حذف ]</a>
            </div>
        </div>
        """

    admin_section = ""
    if user["is_admin"] == 1:
        admin_section = f"""
        <div class="card" style="border: 1px solid #ff9800;">
            <h3 style="color: #ff9800;">👑 لوحة الأدمن (القيادة قوج)</h3>
            
            <h4 style="color:#00d2ff; margin-top:15px;">إنشاء كرت شحن جديد:</h4>
            <form action="/admin/create_voucher" method="post" style="display:flex; gap:10px; margin-bottom:15px;">
                <input type="text" name="code" placeholder="أدخل الكود (مثال: QOJ99)" required style="margin:0;">
                <input type="number" name="points" placeholder="النقاط" value="100" required style="margin:0; width:120px;">
                <button type="submit" style="background:#ff9800; width:auto; margin:0; padding:10px 20px;">إضافة الكرت</button>
            </form>

            <h4 style="color:#bbb;">قائمة الكروت الحالية:</h4>
            <table border="1" style="width:100%; border-collapse:collapse; color:#fff; text-align:center; border-color:#333; margin-bottom:15px;">
                <tr style="background:#222;"><th>الكود</th><th>النقاط</th><th>الحالة</th></tr>
                {vouchers_list_html if vouchers_list_html else "<tr><td colspan='3'>لا توجد كروت</td></tr>"}
            </table>

            <h4 style="color:#bbb;">إدارة الأعضاء:</h4>
            <table border="1" style="width:100%; border-collapse:collapse; color:#fff; text-align:center; border-color:#333;">
                <tr style="background:#222;"><th>ID</th><th>المستخدم</th><th>النقاط</th><th>الإجراءات</th></tr>
                {users_list_html}
            </table>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>القيادة قوج - استضافة كل اللغات</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background: #0d0d11; color: #e0e0e0; padding: 20px; max-width: 900px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #222; padding-bottom: 15px; }}
            .card {{ background: #16161a; padding: 20px; border-radius: 12px; margin-top: 20px; border: 1px solid #282830; }}
            input, select, textarea, button {{ padding: 12px; margin: 5px 0; background: #202026; border: 1px solid #333340; color: #fff; border-radius: 8px; width: 100%; box-sizing: border-box; }}
            button {{ background: #007bff; border: none; cursor: pointer; font-weight: bold; width: auto; padding: 12px 25px; }}
            .btn-green {{ background: #28a745; }}
            .btn-contact {{ display: inline-block; padding: 10px 20px; border-radius: 8px; text-decoration: none; color: white; font-weight: bold; margin: 5px; }}
            .wa {{ background: #25D366; }}
            .tg {{ background: #0088cc; }}
            .footer {{ text-align: center; margin-top: 40px; color: #888; font-size: 13px; border-top: 1px solid #222; padding-top: 15px; }}
            .alert-box {{ background: #2b1d0c; border: 1px solid #ff9800; padding: 12px; border-radius: 8px; font-size: 14px; margin-bottom: 10px; color: #ffca28; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="color:#00d2ff; margin:0;">🌐 القيادة قوج</h2>
            <div>
                مرحباً <b>{user['username']}</b> (رصيدك: <b style="color:#00d2ff;">{user['points']} نقطة</b>) | 
                <a href="/logout" style="color:#dc3545; text-decoration: none; font-weight: bold;">تسجيل خروج</a>
            </div>
        </div>

        {f'<div class="alert-box">{msg}</div>' if msg else ''}

        <!-- 🎫 شحن الكروت -->
        <div class="card" style="border: 1px solid #28a745;">
            <h3>🎫 شحن رصيد بكود هدايا</h3>
            <form action="/use_voucher" method="post" style="display:flex; gap:10px;">
                <input type="text" name="code" placeholder="أدخل كود الشحن (مثال: QOJ2026)" required style="margin:0;">
                <button type="submit" class="btn-green" style="white-space:nowrap; margin:0;">شحن الآن 💳</button>
            </form>
        </div>

        {admin_section}

        <!-- 💻 كتابة كود البوت مع اختيار كافة اللغات -->
        <div class="card">
            <h3>💻 صمّم واكتب كود بوتك (كل اللغات مدعومة)</h3>
            <div class="alert-box">⚠️ تنبيه: يلزم الالتزام بالقوانين. أي أكواد أو أدوات تقع تحت مسئوليتك الكاملة يا قوج.</div>
            <form action="/create_code" method="post">
                <input type="text" name="name" placeholder="اسم البوت الجديد" required>
                <select name="app_type">
                    <option value="python">Python (.py)</option>
                    <option value="node">JavaScript / Node.js (.js)</option>
                    <option value="php">PHP Script (.php)</option>
                    <option value="go">Go Language (.go)</option>
                    <option value="ruby">Ruby Script (.rb)</option>
                    <option value="cpp">C++ Source (.cpp)</option>
                    <option value="rust">Rust Source (.rs)</option>
                    <option value="java">Java Source (.java)</option>
                    <option value="csharp">C# (.NET)</option>
                    <option value="bash">Shell / Bash Script (.sh)</option>
                </select>
                <textarea name="code" rows="8" placeholder="اكتب كود البوت بأي لغة اختيارية هنا..." required></textarea>
                <button type="submit" class="btn-green">حفظ وتشغيل الكود 🚀</button>
            </form>
        </div>

        <!-- 🚀 رفع بوت جاهز لكافة اللغات -->
        <div class="card">
            <h3>🚀 رفع ملف بوت جاهز (أي لغة برمجة)</h3>
            <form action="/upload" enctype="multipart/form-data" method="post">
                <input type="text" name="name" placeholder="اسم البوت" required>
                <select name="app_type">
                    <option value="python">Python (.py)</option>
                    <option value="node">JavaScript / Node.js (.js)</option>
                    <option value="php">PHP (.php)</option>
                    <option value="go">Go (.go)</option>
                    <option value="ruby">Ruby (.rb)</option>
                    <option value="cpp">C++ (.cpp)</option>
                    <option value="rust">Rust (.rs)</option>
                    <option value="java">Java (.java)</option>
                    <option value="csharp">C# (.cs)</option>
                    <option value="bash">Bash Script (.sh)</option>
                </select>
                <input type="file" name="file" required><br><br>
                <button type="submit">رفع الملف وتخزينه</button>
            </form>
        </div>

        <!-- 📂 قائمة البوتات -->
        <div class="card">
            <h3>📂 بوتاتك المرفوعة والمُشغلة</h3>
            {apps_html if apps_html else "<p style='color:#777;'>لا توجد بوتات مرفوعة في حسابك حالياً.</p>"}
        </div>

        <!-- 📞 التواصل والدعم الفني -->
        <div class="card" style="text-align: center;">
            <h3>💬 تواصل مع المطور القيادة قوج</h3>
            <a href="https://wa.me/249916756970" target="_blank" class="btn-contact wa">📱 تواصل واتساب: 0916756970</a>
            <a href="https://t.me/Qoj249" target="_blank" class="btn-contact tg">✈️ تواصل تلجرام: @Qoj249</a>
        </div>

        <div class="footer">
            جميع الحقوق محفوظة © <b>القيادة قوج</b>
        </div>
    </body>
    </html>
    """
                # --- 5. السجل المباشر والأوامر ---
@app.get("/logs/{app_id}", response_class=HTMLResponse)
def view_logs(app_id: int, session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    log_path = os.path.join(LOGS_DIR, f"{app_id}.log")
    logs_content = "لا توجد سجلات بعد لهذا البوت."
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            logs_content = f.read()

    return f"""
    <!DOCTYPE html>
    <html dir="ltr">
    <head>
        <meta charset="UTF-8">
        <title>سجل البوت المباشر - Live Logs</title>
        <style>
            body {{ background: #000; color: #00ff00; font-family: monospace; padding: 20px; }}
            .log-container {{ background: #111; padding: 15px; border-radius: 8px; border: 1px solid #333; height: 80vh; overflow-y: scroll; white-space: pre-wrap; }}
        </style>
    </head>
    <body>
        <h2>📜 Live Terminal Output Log - القيادة قوج</h2>
        <div class="log-container">{logs_content}</div>
        <br>
        <button onclick="location.reload()" style="padding:10px 20px; background:#222; color:#fff; border:1px solid #555; cursor:pointer; font-weight:bold;">تحديث السجل 🔄</button>
    </body>
    </html>
    """

@app.post("/use_voucher")
def use_voucher(code: str = Form(...), session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vouchers WHERE code = ? AND used = 0", (code,))
    voucher = cursor.fetchone()

    if voucher:
        cursor.execute("UPDATE vouchers SET used = 1 WHERE id = ?", (voucher["id"],))
        cursor.execute("UPDATE users SET points = points + ? WHERE id = ?", (voucher["points"], user["id"]))
        conn.commit()
        conn.close()
        send_qoj_alert(f"🎫 تم استخدام كرت شحن بنجاح بواسطة: {user['username']}\nقيمة النقاط: {voucher['points']}")
        return RedirectResponse(url="/?msg=تم شحن الكارت بنجاح! 🎉", status_code=303)

    conn.close()
    return RedirectResponse(url="/?msg=كود الشحن غير صحيح أو تم استخدامه ❌", status_code=303)

@app.post("/admin/create_voucher")
def create_voucher(code: str = Form(...), points: int = Form(...), session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if user and user["is_admin"] == 1:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO vouchers (code, points) VALUES (?, ?)", (code, points))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/create_code")
def create_code(name: str = Form(...), app_type: str = Form(...), code: str = Form(...), session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    ext_map = {
        "python": ".py", "node": ".js", "php": ".php", "go": ".go",
        "ruby": ".rb", "cpp": ".cpp", "rust": ".rs", "java": ".java",
        "csharp": ".cs", "bash": ".sh"
    }
    ext = ext_map.get(app_type, ".py")
    filename = f"{user['id']}_{int(time.time())}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO apps (user_id, name, filename, app_type) VALUES (?, ?, ?, ?)", 
                   (user['id'], name, filename, app_type))
    conn.commit()
    conn.close()
    send_qoj_alert(f"🚀 تم إنشاء كود جديد بواسطة {user['username']}\nاسم البوت: {name} (اللغة: {app_type})")
    return RedirectResponse(url="/", status_code=303)

@app.post("/upload")
async def upload(name: str = Form(...), app_type: str = Form(...), file: UploadFile = File(...), session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    file_path = os.path.join(UPLOAD_DIR, f"{user['id']}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO apps (user_id, name, filename, app_type) VALUES (?, ?, ?, ?)", 
                   (user['id'], name, f"{user['id']}_{file.filename}", app_type))
    conn.commit()
    conn.close()
    send_qoj_alert(f"📁 تم رفع ملف بوت جديد بواسطة {user['username']}\nاسم البوت: {name} (اللغة: {app_type})")
    return RedirectResponse(url="/", status_code=303)

@app.get("/action/{act}/{app_id}")
def action(act: str, app_id: int, session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db()
    cursor = conn.cursor()
    
    if user["is_admin"] == 1:
        cursor.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
    else:
        cursor.execute("SELECT * FROM apps WHERE id = ? AND user_id = ?", (app_id, user["id"]))
    
    app_data = cursor.fetchone()
    
    if app_data:
        file_path = os.path.join(UPLOAD_DIR, app_data["filename"])
        log_path = os.path.join(LOGS_DIR, f"{app_id}.log")

        if act == "start" and app_id not in running_processes:
            log_file = open(log_path, "a", encoding="utf-8")
            cmd = get_run_command(app_data["app_type"], file_path)
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)
            running_processes[app_id] = proc
            process_files[app_id] = log_file
            cursor.execute("UPDATE apps SET status = 'running' WHERE id = ?", (app_id,))
        elif act == "stop" and app_id in running_processes:
            proc = running_processes.pop(app_id)
            proc.terminate()
            if app_id in process_files:
                process_files.pop(app_id).close()
            cursor.execute("UPDATE apps SET status = 'stopped' WHERE id = ?", (app_id,))
        elif act == "delete":
            if app_id in running_processes:
                proc = running_processes.pop(app_id)
                proc.terminate()
                if app_id in process_files:
                    process_files.pop(app_id).close()
            if os.path.exists(file_path):
                os.remove(file_path)
            cursor.execute("DELETE FROM apps WHERE id = ?", (app_id,))
            
        conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/add_points/{target_user_id}")
def add_points(target_user_id: int, session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if user and user["is_admin"] == 1:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET points = points + 50 WHERE id = ?", (target_user_id,))
        conn.commit()
        conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/delete_user/{target_user_id}")
def delete_user(target_user_id: int, session_id: str = Cookie(None)):
    user = get_current_user(session_id)
    if user and user["is_admin"] == 1 and target_user_id != user["id"]:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        cursor.execute("DELETE FROM apps WHERE user_id = ?", (target_user_id,))
        conn.commit()
        conn.close()
    return RedirectResponse(url="/", status_code=303)
  
