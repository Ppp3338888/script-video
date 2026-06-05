import os, sqlite3
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN", "")
GEMINI_MODEL   = "gemini-2.5-flash"
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR    = os.path.join(BASE_DIR, "outputs")
DB_PATH        = os.path.join(BASE_DIR, "app.db")
FPS            = 24
SHOT_SECS      = 3
IMG_W, IMG_H   = 1280, 720

os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ── DB ──────────────────────────────────────────────────────────────────────
def db():
    c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; return c

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS projects(
        id TEXT PRIMARY KEY, title TEXT, script TEXT,
        status TEXT DEFAULT 'pending', video_path TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS shots(
        id TEXT PRIMARY KEY, project_id TEXT, num INTEGER,
        description TEXT, location TEXT, tod TEXT, mood TEXT,
        image_path TEXT, dirty INTEGER DEFAULT 0, version INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS characters(
        id TEXT PRIMARY KEY, project_id TEXT,
        name TEXT, appearance TEXT, last_shot INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS feedback_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT, feedback TEXT, affected TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    """)
    con.commit(); con.close()
