# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArchTransform ("Floor to 3D") converts 2D floor plan images/PDFs into interactive 3D models. A FastAPI backend runs an OpenCV computer-vision pipeline to extract walls/rooms/doors from blueprints; a React frontend renders the result with Three.js.

## Commands

### Backend (FastAPI, Python)

```powershell
cd backend
pip install -r requirements.txt
python main.py          # runs uvicorn on 0.0.0.0:8081 with reload
```

Note: `requirements.txt` is incomplete — the code also imports `motor` (MongoDB), `PyJWT` (`import jwt`), and optionally `google-genai` (Gemini room extraction fallback).

`backend/main.py` sets the Windows selector event loop policy before importing the app — run via `python main.py` on Windows, not bare `uvicorn app.main:app`.

### Frontend (React + Vite)

```powershell
cd frontend
npm install
npm run dev             # vite --host
npm run build
npm run lint            # eslint
```

There is no test runner configured. Files like `backend/test_*.py` are ad-hoc scripts hitting a running server (often port 8081), not pytest suites.

### Configuration

`backend/.env` (parsed by a hand-rolled loader in `app/core/config.py`): `MONGO_URI`, `SECRET_KEY`, `GEMINI_API_KEY_1..3`. MongoDB database name is `floor23d`.

## Architecture

### Data flow

1. Frontend uploads image/PDF via `POST /upload` (`frontend/src/api.js` → `fetchSSEForm`).
2. `backend/app/api/routes/upload.py` streams Server-Sent Events: progress tuples, then a final result. PDFs are rasterized per-page with PyMuPDF; files process concurrently in a thread pool.
3. `app/services/vision/pipeline.py::process_image` is a **generator** — it yields `(percent, message)` progress tuples and finally a dict `{"walls", "rooms", "doors", "width", "height"}` in pixel coordinates.
4. Frontend `engine/engine.js` consumes that raw backend data and builds the 3D scene.

### Vision pipeline (`backend/app/services/vision/`)

- `pipeline.py` — orchestrator: thresholding, wall-thickness estimation, morphology, then room expansion. Behavior is switched by `PIPELINE_VERSION` in `app/core/config.py` (currently `'v7'`).
- `algorithms.py` — the versioned room-expansion algorithms (`_expand_rooms_v4` … `_expand_rooms_v8_polygons`). Old versions are kept intentionally for the version switch.
- `walls.py` — precise wall/door/region geometry extraction (`extract_wall_geometry`, `snap_rooms_to_regions`).
- `core.py` — `_extract_rooms` (room label/seed extraction).
- `gemini.py` — optional AI-based room bounding-box extraction using Gemini (rotates through 3 API keys).

### Backend structure

- `app/main.py` — FastAPI app, CORS `*`, mounts `uploads/` as static, includes routers.
- `app/api/routes/` — `auth.py` (JWT signup/login), `projects.py` (save/load projects in MongoDB, user-scoped), `upload.py` (SSE processing endpoint).
- `app/core/` — `config.py` (env + `PIPELINE_VERSION`), `database.py` (Motor client), `security.py` (JWT via PyJWT).

The many loose scripts in `backend/` root (`fix_*.py`, `rewrite_*.py`, `extract_*.py`, `inject_*.py`, `revert_*.py`, `test_*.py`) are one-off experiment/migration scripts, not part of the running app — the live code is entirely under `backend/app/`.

### Frontend structure

- `src/App.jsx` — routes: `/login`, `/signup`, `/dashboard`, `/annotate` (RoomAnnotation), `/editor`.
- `src/engine/engine.js` (~1900 lines) — the entire Three.js engine as imperative vanilla JS, not React. `Editor.jsx` is a thin wrapper calling `initEngine`/`cleanupEngine` and exported engine functions; the engine manipulates DOM elements (e.g. `#show-room-labels`) directly. It also installs a global `window.fetch` interceptor that prefixes `/`-relative URLs with the API base and attaches the JWT.
- `src/api.js` — API base is hardcoded to `http://<hostname>:8081`; JWT stored in `localStorage`. `fetchSSEForm` parses the upload progress stream.
