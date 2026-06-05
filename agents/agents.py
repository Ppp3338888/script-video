"""
agents.py — all 4 agents in one file

ScriptAgent  → script to shot list
StateAgent   → character continuity
FeedbackAgent→ user change → affected shots
VideoAgent   → images → mp4
"""

import os, uuid
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip
from services.helpers import ask_json, ask_gemini, make_image
from config import OUTPUTS_DIR, FPS, SHOT_SECS

MUSIC = os.path.join(OUTPUTS_DIR, "background_music.mp3")

# ── SCRIPT AGENT ─────────────────────────────────────────────────────────────
SCRIPT_PROMPT = """You are a film script supervisor.
Break this script into shots. For each shot return:
- shot_number (int, from 1)
- description (1-2 sentences, what the camera sees)
- location (e.g. "coffee shop")
- time_of_day (day/night/dawn/dusk)
- mood (neutral/happy/sad/tense/action/romantic/mysterious)
- characters (list of names)

Also return all named characters with name and brief appearance description.

SCRIPT:
{script}

JSON format:
{{
  "shots": [{{"shot_number":1,"description":"...","location":"...","time_of_day":"day","mood":"neutral","characters":[]}}],
  "characters": [{{"name":"...","appearance":"..."}}]
}}"""

def parse_script(project_id, raw_script):
    data = ask_json(SCRIPT_PROMPT.format(script=raw_script))
    shots = [{"id": str(uuid.uuid4()), "project_id": project_id,
               "num": s["shot_number"], "description": s["description"],
               "location": s.get("location",""), "tod": s.get("time_of_day","day"),
               "mood": s.get("mood","neutral"), "characters": s.get("characters",[])}
              for s in data.get("shots",[])]
    chars = [{"id": str(uuid.uuid4()), "project_id": project_id,
               "name": c["name"], "appearance": c.get("appearance","")}
              for c in data.get("characters",[])]
    return shots, chars

# ── STATE AGENT ──────────────────────────────────────────────────────────────
def enrich_shots(shots, chars):
    """Prepend character appearance to shot description for consistent image gen."""
    cmap = {c["name"]: c.get("appearance","") for c in chars}
    for s in shots:
        if s.get("characters"):
            prefix = "Characters: " + ", ".join(
                f"{n} ({cmap.get(n,'')})" if cmap.get(n) else n
                for n in s["characters"]
            ) + ". "
            s["description"] = prefix + s["description"]
    return shots

# ── FEEDBACK AGENT ───────────────────────────────────────────────────────────
FEEDBACK_PROMPT = """You are a film editor AI.
A user wants to change something in a video.
Given the shot list and the feedback, return the IDs of shots that need to be regenerated.
Also return updated descriptions for those shots.

SHOTS:
{shots}

FEEDBACK: {feedback}

Return JSON:
{{
  "affected_shots": [
    {{"id":"...","new_description":"..."}}
  ]
}}"""

def process_feedback(feedback, shots, chars):
    shots_summary = "\n".join(
        f"ID:{s['id']} Shot#{s['num']}: {s['description']}" for s in shots)
    data = ask_json(FEEDBACK_PROMPT.format(shots=shots_summary, feedback=feedback))
    affected = data.get("affected_shots", [])

    # Update descriptions + mark version bump
    id_map = {s["id"]: s for s in shots}
    updated = []
    for a in affected:
        sid = a.get("id")
        if sid and sid in id_map:
            id_map[sid]["description"] = a.get("new_description", id_map[sid]["description"])
            id_map[sid]["dirty"] = True
            id_map[sid]["version"] = id_map[sid].get("version", 1) + 1
            updated.append(id_map[sid])
    return updated   # list of dirty shots with new descriptions

# ── VIDEO AGENT ──────────────────────────────────────────────────────────────
def build_video(project_id, shots):
    clips = []
    for s in sorted(shots, key=lambda x: x["num"]):
        p = s.get("image_path","")
        if p and os.path.exists(p):
            clips.append(ImageClip(p).set_duration(SHOT_SECS))

    if not clips:
        raise ValueError("No images found")

    final = concatenate_videoclips(clips, method="compose")

    if os.path.exists(MUSIC):
        try:
            a = AudioFileClip(MUSIC)
            if a.duration < final.duration:
                from moviepy.editor import concatenate_audioclips
                a = concatenate_audioclips([a] * (int(final.duration/a.duration)+1))
            final = final.set_audio(a.subclip(0, final.duration))
        except Exception as e:
            print(f"[Video] audio skip: {e}")

    out = os.path.join(OUTPUTS_DIR, f"{project_id}_final.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264",
                          audio_codec="aac", verbose=False, logger=None)
    return out
