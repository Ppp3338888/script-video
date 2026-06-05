import os, uuid, json, time
import google.generativeai as genai
from PIL import Image, ImageDraw
from config import GEMINI_API_KEY, GEMINI_MODEL, OUTPUTS_DIR, IMG_W, IMG_H, db
import requests

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)

# ── Gemini ───────────────────────────────────────────────────────────────────
def ask_gemini(prompt):
    for i in range(3):
        try:
            result = _model.generate_content(prompt).text
            time.sleep(4)
            return result
        except Exception as e:
            if i == 2: raise
            wait = 30 * (i + 1)
            print(f"[Gemini] Rate limited, waiting {wait}s...")
            time.sleep(wait)

def ask_json(prompt):
    raw = ask_gemini(prompt + "\n\nReturn ONLY valid JSON. No markdown, no explanation.")
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)

# ── Image generation (Pollinations.ai) ───────────────────────────────────────
MOODS = {
    "tense":(60,20,20),"happy":(200,180,80),"sad":(60,80,110),
    "romantic":(160,80,110),"neutral":(40,50,70),
    "action":(160,60,20),"mysterious":(25,25,55)
}

HF_TOKEN = os.getenv("HF_TOKEN", "")

def make_image(num, desc, location, tod, mood, project_id):
    path = os.path.join(OUTPUTS_DIR, f"{project_id}_s{num:03d}_{uuid.uuid4().hex[:4]}.png")
    prompt = f"Cinematic film still, {tod} lighting, {mood} mood, {location}, {desc}, photorealistic, 16:9"
    try:
        import torch
        from diffusers import StableDiffusionPipeline
        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float32
        )
        pipe.to("cpu")
        image = pipe(prompt, num_inference_steps=20).images[0]
        image = image.resize((IMG_W, IMG_H))
        image.save(path)
        return path
    except Exception as e:
        print(f"[Image] fallback to Pillow: {e}")
        bg = MOODS.get(mood.lower(), MOODS["neutral"])
        img = Image.new("RGB", (IMG_W, IMG_H), bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle([(0,0),(IMG_W,60)], fill=(0,0,0))
        draw.text((20, 20), f"SHOT {num:02d} | {location} | {tod}", fill=(255,210,50))
        words = desc.split(); lines = []; cur = ""
        for w in words:
            if len(cur)+len(w)+1 <= 60: cur += (" " if cur else "")+w
            else: lines.append(cur); cur = w
        if cur: lines.append(cur)
        y = IMG_H//2 - len(lines)*20
        for ln in lines:
            draw.text((IMG_W//2, y), ln, fill=(230,230,230), anchor="mm")
            y += 38
        img.save(path)
        return path
# ── State store (DB helpers) ─────────────────────────────────────────────────
def create_project(title, script):
    pid = str(uuid.uuid4())
    con = db()
    con.execute("INSERT INTO projects(id,title,script,status) VALUES(?,?,?,'processing')",
                (pid, title, script))
    con.commit(); con.close(); return pid

def save_shots(shots):
    con = db()
    for s in shots:
        con.execute("""INSERT OR REPLACE INTO shots
            (id,project_id,num,description,location,tod,mood,image_path,dirty,version)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (s["id"],s["project_id"],s["num"],s["description"],
             s["location"],s["tod"],s["mood"],s.get("image_path",""),
             int(s.get("dirty",False)),s.get("version",1)))
    con.commit(); con.close()

def save_chars(chars):
    con = db()
    for c in chars:
        con.execute("""INSERT OR REPLACE INTO characters(id,project_id,name,appearance,last_shot)
            VALUES(?,?,?,?,?)""",
            (c["id"],c["project_id"],c["name"],c.get("appearance",""),c.get("last_shot",0)))
    con.commit(); con.close()

def get_project(pid):
    con = db()
    p = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p: con.close(); return None
    shots = con.execute("SELECT * FROM shots WHERE project_id=? ORDER BY num",(pid,)).fetchall()
    chars = con.execute("SELECT * FROM characters WHERE project_id=?",(pid,)).fetchall()
    con.close()
    return dict(p), [dict(s) for s in shots], [dict(c) for c in chars]

def set_status(pid, status, video_path=""):
    con = db()
    con.execute("UPDATE projects SET status=?,video_path=? WHERE id=?",
                (status, video_path, pid))
    con.commit(); con.close()

def mark_dirty(pid, shot_ids):
    con = db()
    ph = ",".join("?"*len(shot_ids))
    con.execute(f"UPDATE shots SET dirty=1 WHERE id IN ({ph})", shot_ids)
    con.commit(); con.close()

def update_shot_img(sid, path, version):
    con = db()
    con.execute("UPDATE shots SET image_path=?,dirty=0,version=? WHERE id=?",(path,version,sid))
    con.commit(); con.close()

def log_feedback(pid, feedback, affected_ids):
    con = db()
    con.execute("INSERT INTO feedback_log(project_id,feedback,affected) VALUES(?,?,?)",
                (pid, feedback, json.dumps(affected_ids)))
    con.commit(); con.close()