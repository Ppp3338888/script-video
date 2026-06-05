import os, threading
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from config import OUTPUTS_DIR, init_db
from services.helpers import (create_project, save_shots, save_chars,
                               get_project, set_status,
                               update_shot_img, log_feedback, make_image)
from agents.agents import parse_script, enrich_shots, build_video, process_feedback

app = Flask(__name__)
CORS(app)
init_db()

# ── Pipeline ─────────────────────────────────────────────────────────────────
def run_pipeline(pid, script):
    try:
        shots, chars = parse_script(pid, script)
        shots = enrich_shots(shots, chars)
        save_shots(shots); save_chars(chars)

        for s in shots:
            s["image_path"] = make_image(s["num"], s["description"],
                                         s["location"], s["tod"], s["mood"], pid)
        save_shots(shots)

        video = build_video(pid, shots)
        set_status(pid, "done", video)
    except Exception as e:
        print(f"[Pipeline] ERROR: {e}")
        set_status(pid, "error")

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/generate", methods=["POST"])
def generate():
    d = request.get_json()
    script = d.get("script","").strip()
    if not script: return jsonify({"error":"script required"}), 400
    pid = create_project(d.get("title","Untitled"), script)
    threading.Thread(target=run_pipeline, args=(pid, script), daemon=True).start()
    return jsonify({"project_id": pid, "status": "processing"}), 202

@app.route("/api/project/<pid>")
def project(pid):
    r = get_project(pid)
    if not r: return jsonify({"error":"not found"}), 404
    p, shots, chars = r
    return jsonify({
        "project_id": pid, "title": p["title"], "status": p["status"],
        "video_url": f"/api/video/{pid}" if p.get("video_path") else None,
        "shots": [{"id":s["id"],"num":s["num"],"description":s["description"],
                   "location":s["location"],"tod":s["tod"],"mood":s["mood"],
                   "image_url": f"/api/img/{os.path.basename(s['image_path'])}"
                                if s.get("image_path") else None,
                   "version":s["version"]} for s in shots],
        "characters": [{"name":c["name"],"appearance":c["appearance"]} for c in chars]
    })

@app.route("/api/video/<pid>")
def video(pid):
    r = get_project(pid)
    if not r or not r[0].get("video_path"): return jsonify({"error":"not ready"}), 404
    return send_file(r[0]["video_path"], mimetype="video/mp4")

@app.route("/api/img/<fn>")
def img(fn):
    p = os.path.join(OUTPUTS_DIR, fn)
    if not os.path.exists(p): return jsonify({"error":"not found"}), 404
    return send_file(p, mimetype="image/png")

@app.route("/api/feedback/<pid>", methods=["POST"])
def feedback(pid):
    d    = request.get_json()
    text = d.get("feedback","").strip()
    if not text: return jsonify({"error":"feedback required"}), 400

    r = get_project(pid)
    if not r: return jsonify({"error":"project not found"}), 404
    _, shots, chars = r

    # Phase 2: detect + regenerate affected shots
    dirty = process_feedback(text, shots, chars)
    if not dirty:
        return jsonify({"status":"no_change","message":"No shots affected"})

    for s in dirty:
        s["image_path"] = make_image(s["num"], s["description"],
                                     s["location"], s["tod"], s["mood"], pid)
        update_shot_img(s["id"], s["image_path"], s["version"])

    # Rebuild video preserving unchanged shots
    _, all_shots, _ = get_project(pid)
    video = build_video(pid, all_shots)
    set_status(pid, "done", video)
    log_feedback(pid, text, [s["id"] for s in dirty])

    return jsonify({
        "status": "regenerated",
        "affected_count": len(dirty),
        "affected_shots": [s["num"] for s in dirty],
        "video_url": f"/api/video/{pid}"
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
