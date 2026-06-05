# StateAware Video Generator

Script → structured shots → scene images → MP4 with real-time feedback regeneration.

## Setup
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=your_key" > .env
python app.py
# open http://localhost:5000
```

## Project structure (9 files)
```
video_gen/
├── app.py              # Flask routes + pipeline runner
├── config.py           # Config + SQLite init
├── agents/agents.py    # All 4 agents (Script/State/Feedback/Video)
├── services/helpers.py # Gemini + Pillow image + DB helpers
├── templates/index.html
├── requirements.txt
└── .env
```

## Phase 1 — Script to video
POST /api/generate  →  run_pipeline()  →  parse_script → enrich_shots → make_image × N → build_video

## Phase 2 — Feedback loop
POST /api/feedback/<pid>  →  process_feedback (Gemini finds affected shots)
→ regenerate only dirty shots → rebuild_video (reuses clean images)

## State tracking (SQLite)
- `projects` — title, script, status, video_path
- `shots`    — description, location, tod, mood, image_path, dirty flag, version
- `characters` — name, appearance (keeps visuals consistent)
- `feedback_log` — audit trail of all edits

## Interview talking points
1. **Agentic design** — 4 single-responsibility agents, no frameworks
2. **Incremental regen** — dirty flag + version counter, only affected shots rebuilt
3. **State continuity** — character appearance injected into prompts so image gen stays consistent
4. **No paid APIs** — Pillow for images (swap in SD/DALL-E with one function change)
5. **Music preservation** — audio track carried over when rebuilding video
