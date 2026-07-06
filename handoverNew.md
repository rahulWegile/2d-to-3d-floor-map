# ArchTransform ("Floor to 3D") — Complete Technical Handover Document

> **Read-only analysis.** Nothing in the repository was modified to produce this document. Every claim below is sourced from actual code with file/function references. Where the requested topic does not exist in this repository, it is explicitly marked **"Not found in the codebase."**
>
> One important correction to note up front: this is **not** a Next.js/TypeScript project. It is a **React 19 + Vite + Three.js** frontend with a **FastAPI + OpenCV + MongoDB** Python backend. All sections below document what actually exists.

---

# SECTION 1 — PROJECT OVERVIEW

## What the application does
ArchTransform converts **2D floor-plan images/PDFs into interactive 3D models**. A user uploads a blueprint (PNG/JPEG/PDF); the backend runs a computer-vision + AI pipeline that extracts **walls, rooms, and doors**; the user reviews/edits the detected rooms on a 2D canvas (`/annotate`); then a Three.js scene renders stacked 3D floors with colored, layered room tiles (`/editor`). Projects are persisted per-user in MongoDB.

## Business purpose & end users
- Architects, interior designers, real-estate professionals, or homeowners who have flat blueprints and want a navigable 3D representation without CAD software.
- Problem solved: manual 2D→3D reconstruction is slow; this automates room/wall detection using OpenCV + vision LLMs (NVIDIA Nemotron, Gemini, GPT-4o fallback chain).

## High-level workflow
1. Sign up / log in (JWT) — `frontend/src/pages/Login.jsx`, `backend/app/api/routes/auth.py`
2. Dashboard → upload blueprint(s) — `frontend/src/pages/Dashboard.jsx`
3. Backend streams processing progress over **Server-Sent Events** — `backend/app/api/routes/upload.py`
4. Vision pipeline extracts walls/rooms/doors — `backend/app/services/vision/pipeline.py` `process_image` (a generator)
5. Result saved as a project (`POST /projects/save`) — `backend/app/api/routes/projects.py`
6. User edits rooms per floor at `/annotate` — `frontend/src/pages/RoomAnnotation.jsx`
7. "Build 3D" saves and navigates to `/editor`, where the imperative Three.js engine renders the model — `frontend/src/engine/engine.js`

## Why this architecture
- **FastAPI + SSE**: the CV pipeline takes seconds-to-minutes per file; `process_image` is a Python **generator** yielding `(percent, message)` tuples, streamed to the browser as SSE so the UI shows live progress (`upload.py:24-116`).
- **MongoDB (Motor, async)**: project data is a deeply nested, schema-fluid JSON blob (`rawBackendData` — floors → rooms → polygons → layers). A document store fits naturally; there are no migrations.
- **Imperative Three.js engine outside React**: the 3D scene is stateful, frame-driven, and DOM-heavy; `Editor.jsx` is a thin wrapper that calls `initEngine`/`cleanupEngine`, while the engine binds directly to DOM ids.
- **Versioned algorithms** (`_expand_rooms_v4` … `v8`): the room-detection approach was iterated heavily; old versions are retained behind a `PIPELINE_VERSION` switch (`config.py:12`, currently `'v7'`).

## Main modules
| Module | Location | Responsibility |
|---|---|---|
| Auth | `backend/app/api/routes/auth.py`, `core/security.py` | Signup/login/logout, JWT issue/verify, bcrypt |
| Projects | `backend/app/api/routes/projects.py` | CRUD of projects in MongoDB, user-scoped |
| Upload/SSE | `backend/app/api/routes/upload.py` | Multipart upload, PDF rasterization, thread-pool concurrency, SSE streaming |
| Vision pipeline | `backend/app/services/vision/` | Wall/room/door extraction (OpenCV + Nemotron/Gemini/GPT-4o + EasyOCR) |
| React app | `frontend/src/pages/` | Login, Dashboard, RoomAnnotation, Editor |
| 3D engine | `frontend/src/engine/engine.js` | Three.js scene, room tiles/layers, labels, save/load, fetch interceptor |

## Technologies
**Backend:** Python, FastAPI, Uvicorn, OpenCV (`opencv-python-headless`), NumPy, PyMuPDF (fitz), EasyOCR, Motor (async MongoDB), PyJWT, bcrypt, OpenAI SDK (for NVIDIA Nemotron & OpenRouter GPT-4o), `google-genai` (Gemini).
**Frontend:** React 19, React Router 7, Three.js 0.184, Vite 8, ESLint 10, plain CSS. Native `fetch` (no axios).
**Datastore:** MongoDB, database `floor23d`.

## Architecture diagram

```
                Browser (React 19 SPA, Vite dev server :5173)
                ├── /login /signup ── Login.jsx
                ├── /dashboard ────── Dashboard.jsx
                ├── /annotate ─────── RoomAnnotation.jsx (2D canvas editor)
                └── /editor ───────── Editor.jsx ── engine.js (Three.js, imperative)
                        │
                        │  fetch → http://<hostname>:8081  (api.js + window.fetch interceptor)
                        │  Authorization: Bearer <JWT from localStorage>
                        ▼
        FastAPI "ArchTransform API"  (uvicorn 0.0.0.0:8081, app/main.py)
        ├── /auth/*      auth.py      ── JWT (HS256, 7d) + bcrypt
        ├── /projects/*  projects.py  ── user-scoped project CRUD
        ├── /upload      upload.py    ── SSE stream, ThreadPoolExecutor (≤10 workers)
        │        │
        │        ▼
        │   vision pipeline (services/vision/)
        │   pipeline.process_image  → generator (pct,msg)… → {walls,rooms,doors,width,height}
        │   ├── OpenCV: threshold → wall thickness → morphology → skeleton → Hough lines
        │   ├── walls.py: extract_wall_geometry / snap_rooms_to_regions
        │   ├── core.py: EasyOCR room labels
        │   └── AI: NVIDIA Nemotron → Gemini (3-key rotation) → OpenRouter GPT-4o
        ├── /uploads/*   StaticFiles  ── saved blueprint PNGs
        │
        ▼
        MongoDB "floor23d" (Motor async driver)
        ├── users     {email, username, password(bcrypt)}
        └── projects  {user_id, name, rawBackendData[], settings, lastModified}
```

---

# SECTION 2 — COMPLETE TECH STACK

## Technologies actually present

| Technology | Why used | Where used | Advantages | Alternatives |
|---|---|---|---|---|
| **React 19** | SPA UI | `frontend/src/**` (`react ^19.2.6` in `package.json`) | Component model, hooks, huge ecosystem | Vue, Svelte, Angular |
| **React Router DOM 7** | Client routing | `App.jsx` (`BrowserRouter`, `Routes`, `Navigate`, `useNavigate`, `useLocation`) | Declarative routes | TanStack Router, wouter |
| **Three.js 0.184** | 3D rendering | `engine.js` (WebGLRenderer, OrbitControls, ShapeGeometry) | De-facto WebGL standard | Babylon.js, react-three-fiber |
| **Vite 8** | Dev server + build | `vite.config.js`; scripts `dev`/`build`/`preview` | Fast HMR, ESM-native | Webpack, Parcel |
| **ESLint 10 (flat config)** | Linting | `eslint.config.js` with `@eslint/js`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh` | Hook-rule enforcement | Biome |
| **Native `fetch`** | All HTTP | `api.js`; engine's global interceptor (`engine.js:7-18`) | Zero deps, streaming reader for SSE | axios (not used) |
| **JWT (PyJWT, HS256)** | Stateless auth | `security.py` `create_access_token`/`get_current_user` | No server session store | Session cookies, OAuth |
| **localStorage** | Token/user persistence | Keys `token`, `user_id` set in `Login.jsx:34-38`; `proj_settings_<id>` and legacy `archtransform_*` keys in engine.js | Simple, survives reload | httpOnly cookies (safer vs XSS) |
| **FastAPI** | Backend framework | `app/main.py` | Async, Pydantic validation, SSE via StreamingResponse | Flask, Django |
| **Uvicorn** | ASGI server | `backend/main.py` `uvicorn.run(..., port=8081, reload=True)` | Standard ASGI | Hypercorn |
| **OpenCV + NumPy** | CV pipeline | `pipeline.py`, `walls.py`, `algorithms.py` | Mature image ops (Otsu, Hough, distance transform) | scikit-image |
| **PyMuPDF (fitz)** | PDF → PNG rasterization | `upload.py:30-58` (150 DPI, capped ~2000 px) | Fast, no external binaries | pdf2image+poppler |
| **EasyOCR** | Room label OCR | `core.py:3` (module-level `Reader(['en'], gpu=False)`) | Works offline | Tesseract, cloud OCR |
| **Motor (async MongoDB)** | Persistence | `database.py` → db `floor23d`, collections `users`, `projects` | Non-blocking with FastAPI | PyMongo sync, Beanie ODM |
| **bcrypt** | Password hashing | `auth.py:30,50` | Salted, adaptive cost | argon2 |
| **OpenAI SDK** | Calls NVIDIA Nemotron & OpenRouter GPT-4o | `pipeline.py:238-313`, `gemini.py:90-137` | One client, many OpenAI-compatible providers | httpx direct |
| **google-genai (Gemini)** | Room-box fallback | `gemini.py` — rotates `GEMINI_API_KEY_1..3` across 3 models | JSON response mode | — |
| **Environment variables** | Secrets/config | Hand-rolled `.env` loader in `config.py:3-10` | No python-dotenv dep | python-dotenv, pydantic-settings |
| **npm** | Frontend package mgmt | `package-lock.json` present | Lockfile reproducibility | pnpm, yarn |
| **CSS variables** | Theming tokens | `index.css:1-20` (`--accent: #c58656`, `--glass-blur`, etc.) | Runtime themable | — |
| **React Hooks** | All component state | `useState`/`useEffect`/`useRef` throughout pages | Standard | Class components |

## Requested items NOT present
Per the original template, checked and **Not found in the codebase**: **Next.js**, **TypeScript** (only `@types/react*` for editor IntelliSense; zero `.ts/.tsx` files), **Tailwind**, **Node backend** (backend is Python), **Axios**, **Docker**, **PM2** (closest analog: `start.ps1` PowerShell restart loop), **AWS ECS/ECR**, **GitHub Actions** (no `.github/` at all), **App Router**, **Context API** (`createContext`/`useContext` appear nowhere), **Path aliases** (no alias config in vite.config.js), **Dark mode**, **refresh tokens**, **test runners** (no pytest/jest/vitest config).

---

# SECTION 3 — COMPLETE FOLDER STRUCTURE

```
floor_to_3d/
├── CLAUDE.md                    # AI-assistant project guide (untracked). NOTE: two inaccuracies —
│                                #   claims .env has SECRET_KEY (it doesn't) and omits OPENROUTER/NVIDIA keys.
├── .gitignore                   # node_modules, __pycache__, .env, uploads/, frontend/dist, venvs, *.pyc
├── static/images/login_bg.jpg   # duplicate of frontend/public/images/login_bg.jpg (served via backend /static proxy path)
├── uploads/                     # empty dir at repo root (unused)
├── backend/
│   ├── main.py                  # ENTRYPOINT: Windows selector event-loop policy + uvicorn :8081 reload
│   ├── start.ps1                # PowerShell infinite auto-restart loop for uvicorn
│   ├── requirements.txt         # INCOMPLETE (6 packages; see Section 13/22)
│   ├── .env                     # untracked secrets (names in Section 13)
│   ├── uploads/                 # runtime artifacts: ~1058 PNGs + debug/ (133 PNGs, 2 JSON). Unbounded growth.
│   ├── app/                     # ★ THE LIVE APPLICATION
│   │   ├── main.py              # FastAPI app, CORS *, /uploads static mount, 3 routers
│   │   ├── api/routes/          # auth.py, projects.py, upload.py
│   │   ├── core/                # config.py (env + PIPELINE_VERSION), database.py (Motor), security.py (JWT)
│   │   └── services/vision/     # pipeline.py, algorithms.py, walls.py, core.py, gemini.py, temp.txt (scratch)
│   └── ~35 loose root scripts   # one-off code-surgery/test scripts, NOT part of the app (Section 4.4)
└── frontend/
    ├── index.html               # minimal shell, title "frontend", mounts /src/main.jsx
    ├── vite.config.js           # port 5173, host 0.0.0.0, dev proxy /upload /projects /auth /process /static → :8081
    ├── eslint.config.js         # flat config
    ├── package.json / lock      # 4 deps, 8 devDeps
    ├── test-render.jsx          # ad-hoc SSR smoke test (not wired to anything)
    ├── test_3d.cjs              # ad-hoc three.js geometry sanity script
    ├── public/                  # favicon.svg, icons.svg, images/login_bg.jpg
    ├── dist/                    # build output (gitignored)
    └── src/
        ├── main.jsx             # createRoot → <App/>
        ├── App.jsx              # BrowserRouter + 6 routes
        ├── api.js               # API_BASE, token helpers, fetchApi/fetchApiForm/fetchSSEForm
        ├── index.css            # the real global stylesheet (CSS vars, workspace layout, modals)
        ├── App.css, assets/     # unused Vite-template leftovers
        ├── pages/               # Login.jsx, Dashboard.jsx, RoomAnnotation.jsx, Editor.jsx
        └── engine/
            ├── engine.js        # ★ 2,058-line imperative Three.js engine (see Section 4.3)
            └── engine.js.bak    # stale 1,790-line backup — not imported; ignore
```

**How folders connect:** `frontend/src/pages` call `frontend/src/api.js` (and raw `fetch`) → `backend/app/api/routes` → `core` (auth/db) and `services/vision` (processing) → MongoDB + `backend/uploads/`. `Editor.jsx` delegates entirely to `engine/engine.js`, which itself calls `/projects` and `/upload` endpoints directly.

There is **no** `components/`, `context/`, `hooks/`, `lib/`, `services/`, `interface/`, `docs/`, or `scripts/` folder in the frontend — sub-components (`ProjectCard`, `RenameModal`, `EmptyState`, `UploadModal`) live inline inside `Dashboard.jsx`.

---

# SECTION 4 — COMPLETE FILE ANALYSIS

## 4.1 Backend live files

### `backend/main.py`
Entrypoint. Sets `asyncio.WindowsSelectorEventLoopPolicy()` on Windows (required for Motor/pymongo), then `uvicorn.run("app.main:app", host="0.0.0.0", port=8081, reload=True)`. This is why CLAUDE.md says to run `python main.py`, not bare `uvicorn`.

### `backend/app/main.py`
Creates `FastAPI(title="ArchTransform API")`; `os.makedirs("uploads/debug")` at import; CORS middleware with `allow_origins=["*"]` **and** `allow_credentials=True` (a spec conflict — browsers reject credentialed wildcard CORS); mounts `/uploads` as static files; includes the three routers; `GET /` health message. No lifespan hooks, no global exception handlers.

### `backend/app/core/config.py`
Hand-rolled `.env` loader (lines 3-10): reads `backend/.env` line-by-line, splits on first `=`, strips quotes, **overwrites** `os.environ`. Constants: `PIPELINE_VERSION = 'v7'` (line 12), `SECRET_KEY` (env with hardcoded fallback `"archtransform_super_secret_key_123"`, line 13), `ALGORITHM = "HS256"` (line 14), `MONGO_URI` (default `""`, line 15). **Since `.env` has no `SECRET_KEY`, the hardcoded fallback is what actually signs tokens.**

### `backend/app/core/database.py`
`AsyncIOMotorClient(MONGO_URI)` → `client.floor23d` → exports `users_collection`, `projects_collection`. No indexes created anywhere.

### `backend/app/core/security.py`
- `create_access_token(data)` (line 6): adds `exp = utcnow() + 7 days`, HS256-encodes.
- `get_current_user(authorization: Header)` (line 12): expects `Bearer <token>`, 401 on missing/malformed/expired, returns `payload["sub"]` (the user-id string).
- `get_current_user_optional` (line 22): defined, **never used** anywhere.

### `backend/app/api/routes/auth.py`
Pydantic models `UserSignup{email,username,password}` and `UserLogin{username,password}`. `signup` (line 18): lowercases username/email, 400 on duplicates, bcrypt-hashes, inserts, returns `{success, token, user_id, username}`. `login` (line 38): `$or` lookup by username **or** email, `bcrypt.checkpw`, 401 "Invalid credentials", returns same shape. `logout` (line 57): returns `{success: true}` — **no server-side invalidation** (JWT stays valid 7 days).

### `backend/app/api/routes/projects.py`
All four endpoints depend on `get_current_user`. `save_project` (line 18): upsert — with `project_id` does `replace/update` after 403 ownership check; without, inserts and returns new `project_id`. Document shape: `{user_id, name, rawBackendData, settings, lastModified: time.time()}`. `get_projects` (line 41): 403 unless path `user_id` == JWT sub; returns projects sorted by `lastModified` desc. `rename_project` (line 58, PATCH): raw dict body `{name}`; 404/403/400 guards. `delete_project` (line 74): 404/403 guards. ⚠️ `ObjectId(project_id)` is not wrapped in try/except — malformed ids produce uncaught 500s.

### `backend/app/api/routes/upload.py`
- `POST /upload` (line 15) — **unauthenticated**. Reads all files into memory, returns `StreamingResponse(event_stream, media_type="text/event-stream")`.
- Concurrency: `ThreadPoolExecutor(max_workers=min(10, n_files))` (line 78); worker threads push `(msg_type, idx, payload, extra)` tuples into an `asyncio.Queue` via `run_coroutine_threadsafe`; the async generator drains until a `DONE` sentinel.
- PDFs (lines 30-58): `fitz.open(stream=...)`, per page zoom 150/72 DPI capped so longest side ≈ 2000 px, PNG saved to `uploads/floor_pdf_<i>_<page>_<ms>.png`, `process_image` run; **stops at the first page that yields walls or rooms**.
- Images (lines 59-69): saved as `uploads/floor_img_<i>_<ms>.png`, then processed.
- SSE payloads: `{"status":"progress","progress":<avg across files>,"message":"[fname] msg"}`, terminal `{"status":"success","data":{"floors":[{walls,rooms,doors,imageUrl,width,height}]}}` or `{"status":"error","message":...}`.
- `POST /upload/save-image` (line 121): saves one image without vision processing (used by the frontend's rotate-floor feature), returns `{imageUrl}`.

### `backend/app/services/vision/pipeline.py` — `process_image(img_bytes)` generator
Stages (yield % in parens):
1. (5) decode via `cv2.imdecode`; `ValueError` if undecodable.
2. (15) Otsu inverse threshold; switches to adaptive Gaussian (block 51, C 15) if dark ratio > 0.45 or < 0.02.
3. (25) wall-thickness estimate: per-contour `t = 2·area/perimeter`, median of 3<t<60; then text-erase and morphology (ellipse OPEN ~0.5t to drop furniture, rect CLOSE ~0.8t to bridge door gaps).
4. (32) `extract_wall_geometry(gray)` from walls.py (precise wall mask/regions/doors); falls back gracefully to the morphological mask.
5. (35) skeletonization (`cv2.ximgproc.thinning` if available, else iterative erosion).
6. (45) `Canny(30,100)` → `HoughLinesP` (0.5° theta, adaptive min length/gap) → keep near-axis lines (±12°) → snap to axis → merge collinear segments.
7. (55) normalize walls to 3D: `x = px/width*20 − 10`, `z = (py/height*20 − 10)·aspect` → `{"points":[{x,z},{x,z}]}`.
8. (60+) **rooms, v7 path** (lines 222-449): downscale to ≤1024 px → base64 → **NVIDIA Nemotron** (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`, 20 s timeout) asked for `{name,xmin,ymin,xmax,ymax}` boxes on a 1000×1000 grid → clamp/dedupe → merge distant EasyOCR labels → if geometry has ≥2 regions, `snap_rooms_to_regions`, else `_expand_rooms_v8_polygons`. Fallback 1: **Gemini** (`_extract_rooms_gemini`) if Nemotron yields nothing. Fallback 2: OCR-only seeds (2×2 units) snapped/clipped.
9. doors mapped from `geometry["doors"]` into the same coordinate space.
10. Final yield: `{"walls", "rooms", "doors", "width", "height"}`.

Version switch (lines 450-459): `v6/v5/v4` call their respective functions; ⚠️ the `v3`/`v2` branches reference functions that are **neither defined nor imported** — selecting them would raise `NameError`. `_expand_rooms_v7` is imported but never called.

### `backend/app/services/vision/algorithms.py`
The versioned room-expansion family (retained deliberately):
- `_expand_rooms_v4` (line 470) — core labeled algorithm: distance-transform peaks → connected-component cores → BFS region map → map each OCR/AI label to a region → Voronoi-split shared regions → greedy `expand_from_point` growth with occupancy erasure.
- `_expand_rooms_v5` (159) and `_expand_rooms_v6` (4) — effectively identical: delegate to v4 when labels exist; else building-mask + distance-transform core expansion; write debug PNG/JSON to `uploads/debug/`.
- `_expand_rooms_v7` (316) — v6-style mask + `_expand_rooms_labeled` (775), which uses a **Largest Inscribed Rectangle** solver (`_largest_inscribed_rect`, line 702 — O(H·W) monotonic stack) instead of greedy growth. Not called by the current pipeline.
- `_expand_rooms_ai_clip` (936) — clips AI boxes so they never overlap or cross walls (claimed-mask bookkeeping).
- `_expand_rooms_v8_polygons` (1069) — CV region masks → `approxPolyDP` simplified polygons → nearest-centroid matching of AI names to regions → polygon-accurate rooms. This is the shape source for what users see today.

### `backend/app/services/vision/walls.py`
- `extract_wall_geometry(gray)` (line 241): binarize → stroke-width wall-thickness estimate → thick/thin wall masks → `_seal_openings` (bridges door/window gaps, returns door segments) → flood-fill building footprint → connected-component **regions** (candidate rooms). Returns `{wall_thickness, wall_mask, sealed_mask, building_mask, bbox, doors, label_map, regions}` or `None`.
- `snap_rooms_to_regions(ai_rooms, geometry, h, w)` (line 364): treats CV geometry as authoritative — assigns AI boxes to regions by ≥0.15 pixel overlap; one label per region → LIR tile; multiple labels in an open-plan region → Voronoi split; unclaimed big regions become `"Room"`; keeps unmatched AI boxes only if genuinely outside the building.

### `backend/app/services/vision/core.py`
`_extract_rooms(img, h, w)`: EasyOCR (module-level `Reader` — heavy import side effect, ~seconds + torch dependency), filters out measurement strings (`\d+ x \d+`, quotes), confidence > 0.3, maps text centers to 3D `{name, x, z}`, dedupes within 1.5 units.

### `backend/app/services/vision/gemini.py`
`_extract_rooms_gemini`: rotates `GEMINI_API_KEY_1..3` × models (`gemini-flash-latest`, `gemini-2.5-flash`, `gemini-2.0-flash`) with 1 s backoff, JSON response mode; on total failure falls back to **OpenRouter GPT-4o** (`OPENROUTER_API_KEY`). Returns rooms with a `box_2d` field consumed by v4. Returns `[]` on failure.

## 4.2 Frontend files

### `frontend/src/main.jsx` → `createRoot(#root).render(<App/>)`; imports `index.css`.

### `frontend/src/App.jsx`
`BrowserRouter` with routes (lines 13-18): `/login`, `/signup` (same `Login` component with `isSignupRoute`), `/dashboard`, `/annotate`, `/editor`, and `/` → `Navigate to="/login"`. No lazy loading, no catch-all 404.

### `frontend/src/api.js`
- `API_BASE = http://${window.location.hostname}:8081` (line 1) — hardcoded port/protocol.
- `getToken/setToken/removeToken` (lines 3-5) — localStorage key `token`.
- `fetchApi(endpoint, options)` (7-35): JSON + Bearer header; on non-OK parses `{detail|message}` and throws `Error`.
- `fetchApiForm` (37-62): multipart POST (currently unused by pages).
- `fetchSSEForm(endpoint, formData, onProgress)` (64-115): POSTs FormData, then **manually parses the SSE stream** with `response.body.getReader()` + `TextDecoder`, buffering partial lines, handling `data: ` frames, dispatching on `status` (`progress` → callback, `success` → captured result, `error` → throw). Returns the final `data` payload (with `.floors`).

### `frontend/src/pages/Login.jsx`
Combined login/signup form. Calls `/auth/login` or `/auth/signup`; on success `setToken(data.token)`, `localStorage.setItem('user_id', data.user_id)`, navigate `/dashboard` (lines 34-38). Inline error banner; HTML5 validation only.

### `frontend/src/pages/Dashboard.jsx` (~740 lines)
Guard: no `user_id` → `/login` (442-445). `loadProjects` GETs `/projects/{userId}?t=<now>` (cache-buster). Upload flow `processFiles` (471-503): FormData(`files`) → `fetchSSEForm('/upload')` with live progress → `POST /projects/save` `{user_id, name, rawBackendData: data.floors}` → navigate `/annotate?project_id=...`. Delete (DELETE `/projects/{id}`), rename (PATCH `/projects/{id}/rename` via `RenameModal`), logout (best-effort `POST /auth/logout`, then clear localStorage). Inline sub-components: `ProjectCard`, `RenameModal`, `EmptyState`, `UploadModal` (drag-drop, accepts png/jpeg/pdf, multiple).

### `frontend/src/pages/RoomAnnotation.jsx` (~1,100 lines)
The 2D review/edit canvas. Loads the project by `project_id` query param (raw `fetch` with manual Bearer header). Coordinate helpers map canvas px ↔ 3D units (world spans −10..+10 in X; Z scaled by floor aspect, lines 15-27). Users can: rename rooms, set up to **3 hierarchical layer names** per room, recolor, resize (W×D), drag-move (with cross-floor alignment of the same room index, lines 404-427), draw new room rectangles, delete rooms; and add floors (via `/upload` SSE), delete floors, rotate a floor 90° (client-side canvas rotation uploaded via `/upload/save-image`, plus mathematical transform of room/wall coords, lines 565-662). "Build 3D" (`handleBuild`, 665-692) **saves to the backend and navigates** to `/editor?project_id=...` — data is passed between pages via the database, not router state.

### `frontend/src/pages/Editor.jsx`
Thin wrapper: renders the static DOM scaffold (toolbar, tool panel, `#canvas-container`, `#labels-container`, properties panel, delete modal) whose element **ids the engine binds to**; `useEffect` calls `initEngine(projectId)` and `cleanupEngine()` on unmount (41-48). Imports `uploadAndAddFloor`/`toggleWallMode` that are unused; `wallMode` state is dead. "Annotation" button awaits `saveCurrentProject()` then navigates back.

### `frontend/src/engine/engine.js` (2,058 lines)
Exports: `initEngine`, `cleanupEngine`, `toggleFloorLabels`, `isFloorLabelsVisible`, `saveCurrentProject`, `uploadAndAddFloor`, `toggleWallMode`.
- **Global fetch interceptor (lines 7-18), installed at module import**: rewrites `/`-relative URLs to `http://<hostname>:8081` and attaches `Authorization: Bearer <localStorage.token>`. This is how the engine's relative `fetch('/projects/...')` calls work. It affects *every* fetch on the page.
- `initEngine` (94-152): scene (bg `0xf1f5f9`), PerspectiveCamera 45° at (0,30,30), antialiased WebGLRenderer with shadow map, OrbitControls with damping, ambient + directional light, event listeners, `setupUI()`, auto-load project → `buildBuilding`, start RAF loop.
- **Data → 3D** (`buildBuilding`, 955-1097): each floor becomes a 20-unit-wide plane (height = 20·aspect) at `yOffset = idx * FLOOR_HEIGHT(4)`; blueprint texture applied when `#show-blueprint` checked. Each room polygon becomes a `THREE.Shape` → ShapeGeometry tile, and **every room spawns 3 stacked "layer" tiles** at `y = 0.1 + (layer−1)·0.8` with black edge outlines and an HTML `<div class="room-label">` overlay (1711-1789). Room-name → color mapping: bed→green, bath/wc→cyan, kitchen/dining→red, hall/corridor→pink, digits→yellow, default blue (1722-1728).
- ⚠️ **No real 3D walls exist**: `createManualWall` (1791-1798) computes values then intentionally does nothing ("No inner walls or inner pillars are drawn as requested"), and `updatePillarsHeight` (880-895) clears pillars. Wall selection/outer-wall-hide/wall-mode UI paths are inert; saves fall back to `originalWalls` (1105-1107). The rendered model is floors + colored room tiles + labels.
- Labels: HTML divs positioned each frame by `updateLabels` (1978-2039) projecting world→NDC→pixels; visibility precedence = category filter > isolated group/layer > layer checkboxes/floor visibility.
- Category filters/layer isolation: `updateRoomCategoryFilters` (189-255) builds pill buttons; `selectRoom` (1922-1976) populates the properties panel and per-layer isolation buttons.
- Interactions: raycast click select (stacked-mode piercing pass), keyboard arrows move (±0.25), Shift+arrows scale, Delete removes; wall/floor draw modes with snap-preview lines (wall drawing is inert due to the stub).
- Save (`saveCurrentProject`, 1099-1205): regroups tiles by `groupId` → rebuilds `rawBackendData` → `POST /projects/save` with `settings {wallColor, floorColor, bgColor, wallOpacity, floorOpacity}`; per-project settings also cached in `localStorage[proj_settings_<id>]` (261-308).
- Legacy dead code: `appLogin`, `loadDashboard`, `window.openProject` (the React pages replaced these); `FontLoader`/`TextGeometry` imports unused; `cleanupEngine` (154-168) under-disposes (doesn't dispose geometries/textures, remove label divs, or restore `window.fetch`).

## 4.3 Non-production/stray files
`frontend/src/App.css`, `src/assets/*` (Vite template leftovers, unused), `test-render.jsx`, `test_3d.cjs`, `engine.js.bak`, `backend/v4_backup.txt` (190 KB code dump), `app/services/vision/temp.txt`.

## 4.4 The ~35 loose backend scripts (all tracked in git, none part of the app)
Three families: **code-surgery scripts** that patched `algorithms.py` in place by string replacement during the v4→v8 algorithm churn (`fix_*.py`, `rewrite_v6*.py`, `revert_*.py`, `restore_v4.py`, `copy_v5_to_v6.py`, `inject_*.py`, `add_expand_tetris.py`, `do_refactor.py` — the last generated the current `app/` layout); **extraction scripts/dumps** that pulled v4 source out of an AI CLI transcript (`extract_v4*.py`, `extracted_v4*.py`, `temp_v8.py`, `temp_clip.py`); and **ad-hoc manual tests** (`test_api*.py` hit a running server; `test_pipeline.py`/`test_rooms*.py`/`test_v6.py`/`test_extract.py` call vision functions directly; `test_mongo.py` pings the DB; `evaluate_nims.py`/`test_nemotron_vlm.py` probe NVIDIA NIM — ⚠️ **both contain hardcoded `nvapi-` keys in source; rotate these**). Some tests are stale (they unpack `process_image` as a 4-tuple, which no longer matches the generator API).

---

# SECTION 5 — APPLICATION FLOW

```
User opens site → "/" → Navigate to /login          (App.jsx:18)
        │
   Login/Signup form (Login.jsx)
        │ POST /auth/login {username,password}
        ▼
   auth.py: find user ($or username/email) → bcrypt.checkpw
        │ create_access_token({sub: user_id}, exp=+7d, HS256)
        ▼
   Response {success, token, user_id, username}
        │ setToken → localStorage.token ; localStorage.user_id   (Login.jsx:34-38)
        ▼
   navigate('/dashboard')
        │ Dashboard guard: no user_id → back to /login (Dashboard.jsx:442)
        │ GET /projects/{user_id}?t=<now>  (Bearer header via fetchApi)
        ▼
   Project cards render (name, floor count, lastModified)
        │
   [Upload blueprint] ──► POST /upload (multipart, SSE)
        │    ◄─ data:{status:progress, progress, message}  (live bar)
        │    ◄─ data:{status:success, data:{floors:[...]}}
        │ POST /projects/save {user_id, name, rawBackendData: floors}
        ▼
   /annotate?project_id=X  → edit rooms/layers/floors → auto-save via /projects/save
        │  [Build 3D]: save, then navigate
        ▼
   /editor?project_id=X → Editor.jsx useEffect → initEngine(X)
        │  engine: GET /projects/{user_id} → find project → buildBuilding(rawBackendData)
        │  RAF loop: controls.update → updateLabels → render
        ▼
   [Save Project] → engine.saveCurrentProject → POST /projects/save
        │
   Logout (Dashboard): POST /auth/logout (no-op server-side)
        → removeToken + remove user_id → /login. Token itself stays valid until exp.
```

Key nuance: **pages never pass data to each other in memory** — every page re-fetches the project from MongoDB using the `project_id` URL param plus the localStorage token. The database is the single source of truth between routes.

---

# SECTION 6 — ROUTING

- **Router:** `react-router-dom` v7 `BrowserRouter` (`App.jsx`). This is client-side routing only — there is no Next.js App Router, no file-based routing, no server components.
- **Routes:** `/login`, `/signup`, `/dashboard`, `/annotate?project_id=`, `/editor?project_id=`, `/` (redirect to `/login`). All eagerly imported — **no lazy loading, no Suspense, no route-level code splitting.**
- **Public routes:** `/login`, `/signup`. **Protected routes:** protection is *ad-hoc per page*, not a wrapper component: Dashboard redirects to `/login` when `localStorage.user_id` is absent (442-445); RoomAnnotation redirects to `/dashboard` when `project_id` is missing or the project can't load (131-150); Editor redirects to `/dashboard` when `project_id` is missing (31-39). Note the guard checks `user_id` presence, not token validity — an expired token surfaces later as API 401s (Dashboard then logs the user out, 452-454).
- **Layouts / nested routes / dynamic segments:** none — flat route list; the "dynamic" part is query strings (`?project_id=`), not path params.
- **404 handling:** **Not found in the codebase** — no `path="*"` route; unknown URLs render a blank page.
- **Loading UI:** per-page (`RoomAnnotation` full-screen "Loading floor plan…", Editor's engine-controlled `#loading` overlay, Dashboard's SSE progress bar). **Error UI:** inline banners/modals (Section 17). **Route metadata:** none; `<title>` is the static "frontend" from `index.html`.

---

# SECTION 7 — AUTHENTICATION

**Token lifecycle**

```
signup/login (auth.py)
  └─ create_access_token({sub: str(user._id)})     security.py:6
       payload = { sub: "<mongo ObjectId str>", exp: now + 7 days }
       HS256, SECRET_KEY (⚠️ hardcoded fallback in config.py:13 is what actually runs)
            │
            ▼
  frontend: localStorage.setItem('token', ...)      api.js:4 via Login.jsx:34
            │
   attached on every request as  Authorization: Bearer <token>
     • api.js helpers (fetchApi/fetchApiForm/fetchSSEForm)
     • engine.js global fetch interceptor (engine.js:7-18)
     • RoomAnnotation's raw fetches (manual header)
            │
            ▼
  backend: get_current_user (security.py:12) → jwt.decode → returns sub
     routes compare sub to user_id / project.user_id → 403 on mismatch
            │
  expiry: after 7 days jwt.decode raises → 401 "Invalid or expired token"
  logout: POST /auth/logout returns {success:true} — token NOT invalidated;
          client just deletes localStorage keys (Dashboard.jsx:457-463)
```

- **Refresh token / silent refresh / session provider:** **Not found in the codebase.** One 7-day access token; on expiry the user re-logs in (Dashboard's 401 handler force-logs-out).
- **Password storage:** bcrypt with per-password salt (`auth.py:30`).
- **Login identifier:** the `username` field accepts username *or* email (`$or` query, auth.py:41-46); both are lowercased at signup.
- **Security observations (documented, not fixed):** JWT in localStorage is readable by any XSS payload; `SECRET_KEY` effectively runs on its committed hardcoded fallback; logout is client-side only; `/upload` and `/upload/save-image` require **no auth at all**; `get_projects` returns all fields of all of a user's projects (fine for one user, heavy payloads at scale).

---

# SECTION 8 — API LAYER

All endpoints live under `backend/app/api/routes/`. Base URL: `http://<hostname>:8081` (`api.js:1`); Vite dev proxy also forwards `/upload /projects /auth /process /static` to :8081 (`vite.config.js:10-16`) — `/process` is proxied but no code calls it.

| Endpoint | Method | Auth | Purpose | Request | Success response | Called from |
|---|---|---|---|---|---|---|
| `/auth/signup` | POST | none | Create account | `{email, username, password}` | `{success, token, user_id, username}` | Login.jsx:24-32 (also legacy engine.js:339) |
| `/auth/login` | POST | none | Log in (username or email) | `{username, password}` | same as signup | Login.jsx |
| `/auth/logout` | POST | none | Client-side logout ack | — | `{success: true}` | Dashboard.jsx:457, engine.js:477 |
| `/projects/save` | POST | Bearer | Create/update project | `{user_id, project_id?, name, rawBackendData[], settings?}` | `{project_id}` | Dashboard (create), RoomAnnotation (edits/floors/rotate/build), engine.saveCurrentProject |
| `/projects/{user_id}` | GET | Bearer | List user's projects | path param | `{projects:[{project_id, name, rawBackendData, settings, lastModified}]}` | Dashboard.loadProjects, RoomAnnotation load, engine.loadEditorProject |
| `/projects/{project_id}/rename` | PATCH | Bearer | Rename | `{name}` | `{renamed: true}` | Dashboard.jsx:514-527 |
| `/projects/{project_id}` | DELETE | Bearer | Delete | path param | `{deleted: true}` | Dashboard.jsx:505-512 |
| `/upload` | POST | **none** | Process blueprints, stream progress | multipart `files[]` | SSE stream → `{status:success, data:{floors:[{walls,rooms,doors,imageUrl,width,height}]}}` | Dashboard.processFiles, RoomAnnotation.addFloor, engine.uploadAndAddFloor |
| `/upload/save-image` | POST | **none** | Save image without processing | multipart `file` | `{imageUrl}` | RoomAnnotation.rotateFloor |
| `/uploads/<file>` | GET | none | Static blueprint images | — | PNG | floor textures (engine TextureLoader), annotate canvas |
| `/` | GET | none | Health message | — | `{message: "...running..."}` | not called by frontend |

- **Headers:** `Content-Type: application/json` + `Authorization: Bearer` (JSON calls); multipart boundary auto-set for FormData.
- **Error handling:** backend raises `HTTPException` (400/401/403/404); frontend `fetchApi` throws `Error(detail || message || text)`; SSE errors arrive as `{status:"error"}` frames and are thrown by `fetchSSEForm`.
- **Retry logic:** **Not found in the codebase** (no retries anywhere; Nemotron client is even configured `max_retries=0`).
- **RPC pattern / masterdata APIs:** **Not found in the codebase.** Plain REST + one SSE endpoint.

---

# SECTION 9 — STATE MANAGEMENT

- **No global state library and no React Context** — verified: `createContext`/`useContext` appear nowhere. No Redux/Zustand/MobX.
- **Local `useState` per page** is the only React state: e.g. Dashboard's `projects/showUpload/uploadProgress/renamingProject` (429-437); RoomAnnotation's ~20 state atoms (floors, rooms, selectedIdx, mode, drag, modals…, 94-113).
- **Refs as escape hatches:** RoomAnnotation keeps `roomsRef/floorsRef/activeFloorIdxRef` mirrored via effects (126-128) so canvas mouse handlers and async callbacks read fresh values without stale closures; `imageCache` ref memoizes blueprint images.
- **Cross-page state** is exactly three channels: **URL query params** (`project_id`), **localStorage** (`token`, `user_id`, `proj_settings_<id>`, legacy `archtransform_*` keys), and **the backend/MongoDB** (each page refetches).
- **Engine state lives outside React entirely** — module-level variables in engine.js (`scene`, `floorsData`, `activeFloorIndex`, `selectedRoomLabel`, `hiddenLabelFloors`, plus `window.activeRoomFilterNames`). The React↔engine bridge is deliberately primitive: the engine reads DOM checkboxes (e.g. `#show-room-labels`) every frame rather than receiving props (noted in `Editor.jsx:15`).
- **Memoization:** **Not found in the codebase** — no `useMemo`, `useCallback`, or `React.memo`. Re-renders are contained because pages are large single components; canvas and Three.js drawing bypass React reconciliation entirely.
- **Custom hooks:** **Not found in the codebase.**

---

# SECTION 10 — COMPONENT ARCHITECTURE

Component tree:

```
<App> (BrowserRouter)
 ├─ /login, /signup → <Login isSignupRoute?>          (one component, two routes)
 ├─ /dashboard → <Dashboard>
 │    ├─ <ProjectCard> ×N   (inline, Dashboard.jsx:9-164; hover, rename/delete, inline confirm)
 │    ├─ <RenameModal>      (166-262)
 │    ├─ <EmptyState>       (264-300)
 │    └─ <UploadModal>      (302-422; drag-drop, SSE progress bar)
 ├─ /annotate → <RoomAnnotation>    (single ~1,100-line component: canvas + side panels + modals)
 └─ /editor → <Editor>              (thin DOM scaffold)
       └─ engine.js (imperative Three.js — NOT React; owns everything inside #canvas-container)
```

- **Reusable components:** effectively none shared across pages — each page is self-contained; there is no `components/` directory. Composition is per-file (Dashboard's four inline sub-components receive props like `proj`, `onOpen`, `onDelete`, `onRename`).
- **Providers/layout components:** **Not found in the codebase.**
- **Lifecycle:** functional components + hooks only. The critical lifecycle pairing is Editor's `useEffect(() => { initEngine(id); return () => cleanupEngine(); }, [projectId])` (`Editor.jsx:41-48`).
- **Rendering split:** React renders chrome (panels, buttons, modals); the annotate canvas is drawn manually via 2D context (`draw`/`drawRoom`, RoomAnnotation.jsx:167-240); the editor viewport is WebGL managed by the engine's RAF loop; room labels are absolutely-positioned HTML divs updated every frame (engine.js:1978-2039).

---

# SECTION 11 — DATABASE ANALYSIS

**Searched the entire repository:** migration files, SQL, Prisma, TypeORM, Sequelize, Knex, stored procedures, triggers, views, ER docs — **Not found in the codebase.** The datastore is **MongoDB** (schemaless), accessed via **Motor** (`database.py`). Database name: **`floor23d`**. Two collections. No indexes are created anywhere; no soft delete; no versioning/audit tables; the only "timestamp" is `lastModified` on projects (users have no `created_at`).

## Reconstructed schema (from actual insert/update/find calls)

### `users` (written in `auth.py:31`)
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | PK; its string form is the JWT `sub` and the `user_id` everywhere |
| `email` | string | lowercased; uniqueness enforced **in application code only** (no unique index — race condition possible) |
| `username` | string | lowercased; same app-level-only uniqueness |
| `password` | string | bcrypt hash |

### `projects` (written in `projects.py:23-29`)
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | PK; exposed as `project_id` string |
| `user_id` | **string** | "FK" to `users._id` — stored as string, not ObjectId; no DB-level referential integrity; every query ownership-checks against the JWT sub |
| `name` | string | project display name |
| `rawBackendData` | array | the entire model (below) |
| `settings` | object/null | `{wallColor, floorColor, bgColor, wallOpacity, floorOpacity}` (written by engine.saveCurrentProject:1166-1182) |
| `lastModified` | float | `time.time()` epoch seconds; used for sort |

### Embedded `rawBackendData` document shape (produced by pipeline.py / edited by frontend)
```
rawBackendData: [                      // one entry per floor
  {
    width:  number,                    // 20 after engine save; original pixel width from pipeline
    height: number,                    // pixel height / aspect-derived
    imageUrl: "/uploads/<file>.png?t=...",
    walls: [ { points: [{x,z},{x,z}] } ],          // axis-snapped segments in −10..+10 space
    doors: [ ... ],                                 // from walls.py door detection
    rooms: [ {
        name: string,
        x: number, z: number, w: number, h: number, // center + size, 3D units
        polygon: [{x,z}, ...],                       // room outline
        color: string,                               // hex, user-editable
        groupId: string|number,                      // ties the 3 layer tiles together
        layerNames: [string, string, string],        // 3 hierarchical zone names
        layers: [{name, color, ...}]                 // optional per-layer detail
    } ]
  }
]
```

## ER diagram

```
┌───────────────────────┐          ┌─────────────────────────────────────┐
│ users                 │ 1      N │ projects                            │
│  _id (PK, ObjectId)   │──────────│  _id (PK, ObjectId)                 │
│  email    (app-unique)│          │  user_id (string ref → users._id)   │
│  username (app-unique)│          │  name                               │
│  password (bcrypt)    │          │  rawBackendData [floors[rooms...]]  │
└───────────────────────┘          │  settings {colors, opacities}       │
                                   │  lastModified (epoch float)         │
                                   └─────────────────────────────────────┘
        (floors/rooms/walls/doors are EMBEDDED documents, not collections)
```

**Normalization:** deliberately denormalized — one project document embeds the full geometry, so a single `find_one`/`replace` covers every load/save. Trade-offs: no partial updates (every save rewrites the whole `rawBackendData`), document size grows with floors, and Mongo's 16 MB document cap is a distant but real ceiling.

**CRUD mapping:** Create → `insert_one` (signup, project save without id). Read → `find_one` ($or login, ownership checks), `find().sort(lastModified,-1)` (project list). Update → full `replace`/`update` on save; `$set {name,lastModified}` on rename. Delete → `delete_one` (hard delete; no soft-delete flag).

---

# SECTION 12 — DATA FLOW

```
[Upload]  Browser file input / drag-drop
   → FormData("files", …)                       Dashboard.jsx:471
   → fetchSSEForm POST /upload  ────────────────  api.js:64
        upload.py: read files into memory → ThreadPoolExecutor(≤10)
            per file thread:
              PDF? → PyMuPDF rasterize 150 DPI (≤2000px) → PNG in uploads/
              process_image() generator:
                 (pct,msg) tuples ──queue──► SSE "progress" frames ──► progress bar
                 final dict {walls,rooms,doors,width,height}
        all done → SSE "success" {floors:[…]}
   → POST /projects/save {rawBackendData: floors} → MongoDB projects.insert_one
   → navigate /annotate?project_id=…

[Annotate] GET /projects/{user_id} → find project → normalize rooms → <canvas> drawing
   user edits (drag/resize/rename/layers/color) → React state (rooms[])
   Build 3D → merge into floors → POST /projects/save → navigate /editor?project_id=…

[Editor]  initEngine → GET /projects/{user_id} → buildBuilding(rawBackendData)
   floors → PlaneGeometry (+blueprint texture from /uploads/…)
   rooms  → THREE.Shape polygons → 3 stacked layer tiles + HTML labels
   RAF loop: OrbitControls → updateLabels (project 3D→2D) → WebGL render
   Save → regroup tiles by groupId → POST /projects/save → MongoDB replace
```

The invariant to remember: **pixel space (blueprint) → normalized 3D space** happens once, in the backend: `x = px/width·20 − 10`, `z = (py/height·20 − 10)·aspect` (`pipeline.py:193-202`). Everything downstream (annotate canvas, engine, saved documents) works in that ±10-unit space; the annotate page converts it back to canvas pixels with its own helpers (RoomAnnotation.jsx:15-27).

---

# SECTION 13 — ENVIRONMENT VARIABLES

Loaded by the hand-rolled parser in `config.py:3-10` from `backend/.env` (present, untracked; **no `.env.example` exists**). The frontend uses **no** env vars at all (no `import.meta.env` anywhere; API host is derived from `window.location.hostname` at runtime).

| Variable | Purpose | Read at | Fallback | Risk if missing |
|---|---|---|---|---|
| `MONGO_URI` | MongoDB connection string | `database.py` via config.py:15 | `""` | Motor client fails on first query → all auth/project endpoints 500 |
| `SECRET_KEY` | JWT signing key | config.py:13 | `"archtransform_super_secret_key_123"` (hardcoded, committed) | ⚠️ **Not in the actual `.env`** — the fallback is live. Anyone reading the repo can forge tokens. |
| `GEMINI_API_KEY_1/_2/_3` | Gemini fallback room extraction | `gemini.py:47-49` | skip | Gemini fallback silently unavailable; pipeline degrades to OCR-only |
| `OPENROUTER_API_KEY` | GPT-4o last-resort fallback | gemini.py:96 | — | that fallback fails; caught, returns `[]` |
| `NVIDIA_API_KEY` | Primary Nemotron room detection | `pipeline.py:245` | `""` | v7's primary AI path fails per-image → falls back to Gemini/OCR (slower, worse rooms) |

Also security-relevant: `evaluate_nims.py` and `test_nemotron_vlm.py` contain **hardcoded `nvapi-` keys committed to git** — these should be rotated. `PIPELINE_VERSION='v7'` and `ALGORITHM='HS256'` are code constants, not env vars. There is no production/development split — one config for all environments.

---

# SECTION 14 — DEPLOYMENT

**Docker, docker-compose, PM2, GitHub Actions, AWS ECS/ECR, nginx, Procfile, CI/CD of any kind: Not found in the codebase** (no `.github/` directory exists). This project currently runs **only as a local Windows dev setup**:

```
Terminal 1: cd backend  → python main.py          (uvicorn 0.0.0.0:8081, reload)
            (or start.ps1: infinite restart loop around uvicorn)
Terminal 2: cd frontend → npm run dev             (vite 0.0.0.0:5173, proxy → 8081)
Prereqs:    MongoDB reachable at MONGO_URI; backend/.env populated;
            pip install -r requirements.txt PLUS motor, bcrypt, PyJWT, easyocr,
            openai, google-genai (requirements.txt is incomplete)
```

Build process: `npm run build` produces `frontend/dist/` (exists locally, gitignored) — but nothing serves it; there is no static-hosting or reverse-proxy config. Backend has no pinned dependency versions, no lockfile, no `pyproject.toml`. `--host`/`0.0.0.0` on both servers means they're LAN-exposed in dev. Anything a new team wants for production (containerization, TLS, process supervision, artifact pipeline) must be built from scratch.

---

# SECTION 15 — SECURITY

Documented as-is (no fixes applied):

1. **JWT secret effectively hardcoded** — `.env` lacks `SECRET_KEY`, so the committed fallback `archtransform_super_secret_key_123` signs all tokens (`config.py:13`). Token forgery is trivial for anyone with repo access.
2. **Token in localStorage** (`api.js:4`) — readable by any XSS payload; 7-day lifetime with no server-side revocation (logout is a no-op server-side, `auth.py:57-59`).
3. **Unauthenticated upload endpoints** — `POST /upload` and `POST /upload/save-image` have no auth dependency (`upload.py:15,121`); anyone who can reach port 8081 can consume CPU/AI-API credits and write files to disk (unbounded `uploads/` growth; `save_image` doesn't validate content type).
4. **CORS misconfiguration** — `allow_origins=["*"]` with `allow_credentials=True` (`app/main.py:13-19`) is spec-invalid for credentialed requests and signals "accept anyone" intent.
5. **World-readable uploads** — `/uploads` static mount exposes every user's blueprints and `uploads/debug/` dumps to anyone with the URL; filenames are guessable timestamps.
6. **Committed API keys** — live-looking `nvapi-` keys hardcoded in `evaluate_nims.py` / `test_nemotron_vlm.py` (tracked in git history). Rotate.
7. **Authorization model** (the good part): every `/projects/*` route verifies ownership against the JWT `sub` before acting (403s in projects.py:21,44,64,80). Passwords are properly bcrypt-hashed.
8. **Input validation:** Pydantic models on auth/save bodies; but `rename` takes a raw dict, `ObjectId()` calls can 500 on malformed ids, and there is no upload size/type limit or rate limiting.
9. **CSRF:** low risk in practice (Bearer-header auth, not cookies), but the unauthenticated upload endpoint is callable cross-site.
10. **Transport:** plain `http://` everywhere; no HTTPS, no security headers (CSP/HSTS), no secrets management beyond `.env`.

---

# SECTION 16 — PERFORMANCE

**What exists:**
- Backend concurrency: files process in parallel in a thread pool (≤10 workers, `upload.py:78`); CPU-bound OpenCV releases the GIL enough for this to help; SSE keeps the browser responsive.
- Image capping: PDFs rasterized to ≤~2000 px; AI input downscaled to ≤1024 px JPEG q85 (pipeline.py:229-235).
- Frontend: blueprint image cache ref (RoomAnnotation `imageCache`), cache-busting `?t=` params, damped OrbitControls, `logarithmicDepthBuffer`.
- v7's `_largest_inscribed_rect` is an O(H·W) monotonic-stack solver (algorithms.py:702) — algorithmically sound.

**Not found in the codebase:** lazy loading/code splitting (all routes eager; the whole Three.js engine ships in the main bundle), `useMemo`/`useCallback`/`React.memo`, HTTP caching headers, service workers, CDN config, bundle analysis.

**Actual bottlenecks to know about:**
1. **EasyOCR at import** (`core.py:3`) — the model loads when the vision module is first imported, delaying server startup and pulling in torch.
2. **AI latency dominates**: Nemotron (20 s timeout) → possibly 3 Gemini keys × 3 models with sleeps → OpenRouter; worst-case a single image can burn minutes in fallbacks.
3. **Whole-file memory reads**: every upload is buffered fully in RAM before processing (upload.py:20-22).
4. **`GET /projects/{user_id}` returns every project's full `rawBackendData`** — the dashboard only needs names/counts; payloads grow linearly with project sizes.
5. **Engine leaks across mounts**: `cleanupEngine` doesn't dispose geometries/materials/textures or remove label divs (engine.js:154-168); repeated editor visits accumulate GPU/DOM garbage.
6. **Per-frame DOM writes**: `updateLabels` repositions every label div every frame (engine.js:1978-2039).
7. **Unbounded `uploads/`** (~1,058 PNGs already) — no cleanup job.

---

# SECTION 17 — ERROR HANDLING

**Backend:** explicit `HTTPException`s (400/401/403/404) in routes; upload workers catch everything, print `traceback.format_exc()`, and emit SSE `{status:"error"}` (upload.py:70-73); each AI provider call is try/excepted and falls through the Nemotron→Gemini→OpenRouter→OCR chain; `extract_wall_geometry` failures degrade to the morphological mask. **No logging module** — all diagnostics are `print()`. **No global exception handler** — unexpected errors (e.g. malformed ObjectId, Mongo connection failure) surface as raw 500s.

**Frontend:** `fetchApi` normalizes error bodies to thrown `Error(detail||message||text)` (api.js:23-32); `fetchSSEForm` throws on `error` frames while deliberately swallowing partial-JSON frame noise (api.js:105-109). Per page: Login shows an inline banner; Dashboard shows `error:`-prefixed status in the upload modal, force-logs-out on 401, but rename/delete failures are **silent** (`console.error` only); RoomAnnotation uses custom notice/confirm modals for floor deletion but native `alert()` for add-floor/rotate/build failures, and redirects to `/dashboard` on load failure; the engine paints save success/failure onto the Save button itself (engine.js:1186-1204). **Toast library, retry logic, error boundaries: Not found in the codebase.**

---

# SECTION 18 — COMPLETE DEPENDENCY GRAPH

```
FRONTEND                                      BACKEND
main.jsx ─► App.jsx ─► react-router           backend/main.py ─► app/main.py
                │                                    │               ├─ core/config.py (.env loader)
   ┌────────────┼──────────────┐                     │               ├─ api/routes/auth.py ──► core/security.py ─► config
   ▼            ▼              ▼                     │               │        └────────────► core/database.py ─► config
Login.jsx  Dashboard.jsx  RoomAnnotation.jsx         │               ├─ api/routes/projects.py ─► security + database
   │            │              │                     │               └─ api/routes/upload.py ─► services/vision/pipeline.py
   └────────────┴───────┬──────┘                     │                          │
                        ▼                            │        ┌─────────────────┼──────────────────┐
                     api.js  (fetchApi/fetchSSEForm) │        ▼                 ▼                  ▼
                        │                            │   walls.py         algorithms.py        core.py (EasyOCR)
Editor.jsx ─► engine/engine.js ─► three.js           │   (geometry)       (v4…v8 expansion)        │
                │  (also installs window.fetch       │        └────────► gemini.py (Gemini/GPT-4o fallback)
                │   interceptor used by ALL pages'   │
                │   relative fetches)                ▼
                └──────────── HTTP :8081 ───────► MongoDB floor23d (users, projects)
```

Notable coupling: engine.js depends on Editor.jsx's DOM ids (a hidden contract); pipeline.py depends on all four sibling vision modules; nothing imports the loose backend scripts.

---

# SECTION 19 — COMPLETE EXECUTION FLOW (from `npm run dev` / `python main.py` to pixels)

**Backend startup:** `python main.py` → Windows selector event-loop policy set → `uvicorn.run("app.main:app", 0.0.0.0:8081, reload)` → importing `app.main` runs `config.py` (parses `.env` into `os.environ`), creates the Motor client (lazy — no connection yet), `os.makedirs("uploads/debug")`, registers CORS + static mount + routers. First import of the vision package loads **EasyOCR's model into memory** (the slow part of startup).

**Frontend startup:** `npm run dev` → Vite starts an ESM dev server on 0.0.0.0:5173 with the React plugin (JSX transform + Fast Refresh) and the API proxy. The browser loads `index.html` → `/src/main.jsx` → Vite serves each module transformed on demand. Importing `App.jsx` transitively imports the pages; importing `Editor.jsx` imports `engine.js`, whose **top-level side effect immediately replaces `window.fetch`** (engine.js:7-18) — this happens at app load, not editor mount. `createRoot(...).render(<App/>)` runs React's concurrent renderer (no SSR, so **no hydration** — pure client render), `BrowserRouter` reads `location.pathname`, `/` matches `Navigate → /login`, Login renders, browser paints.

**Interactive loop (editor):** navigating to `/editor?project_id=X` mounts Editor → effect calls `initEngine(X)` → engine appends a `<canvas>` to `#canvas-container`, fetches the project, builds meshes, and starts `requestAnimationFrame(animate)`; every frame: `controls.update()` (damping) → `updateLabels()` (3D→screen projection of label divs) → `renderer.render(scene, camera)`. React is idle during this; only toolbar clicks re-enter React. HMR note: Vite re-imports modules on edit; the engine guards double-init via `if (renderer) return` (engine.js:96).

---


---

# SECTION 20— PROJECT SUMMARY (Handover One-Pager)

**Architecture:** React 19 + Vite SPA ⇄ (REST + SSE, Bearer JWT) ⇄ FastAPI :8081 ⇄ OpenCV/AI vision pipeline + MongoDB `floor23d`. Imperative Three.js engine mounted by a thin React wrapper. The database is the inter-page message bus.

**Key flows:** upload → SSE-streamed `process_image` → `rawBackendData` floors → `/projects/save` → annotate (2D canvas edit) → editor (3D tiles/layers). Auth: bcrypt + HS256 JWT (7d) in localStorage.

**Critical files:** `backend/app/services/vision/pipeline.py` (the product's core), `walls.py` / `algorithms.py` (geometry/room logic), `upload.py` (SSE/concurrency), `projects.py` + `security.py` (data/auth), `config.py` (`PIPELINE_VERSION='v7'`, env), `frontend/src/engine/engine.js` (3D + fetch interceptor), `RoomAnnotation.jsx` (most complex UI), `api.js` (SSE client).

**Critical env vars:** `MONGO_URI`, `NVIDIA_API_KEY` (primary room AI), `GEMINI_API_KEY_1..3`, `OPENROUTER_API_KEY`; `SECRET_KEY` should exist but currently runs on a committed fallback.

**Known limitations / risks:** no walls rendered in 3D (intentional stub); unauthenticated `/upload`; forgeable JWT secret; hardcoded `nvapi-` keys in two tracked scripts; incomplete unpinned requirements.txt; no tests/CI/Docker/logging/indexes; unbounded public `uploads/`; engine cleanup leaks; `v2/v3` pipeline branches crash; ~35 dead scripts committed; CLAUDE.md has two factual drifts (claims `SECRET_KEY` is in `.env`; omits OPENROUTER/NVIDIA keys).

**Future scope implied by the code:** re-enabling wall extrusion (stubs and `originalWalls` are preserved for it), `_expand_rooms_v7`/LIR path activation, door rendering (data exists, unused by the engine), and real deployment infrastructure.

**Debugging entry points:** SSE issues → `upload.py` queue plumbing + `api.js:64-115`; bad room detection → `uploads/debug/` PNG/JSON dumps + `PIPELINE_VERSION`; 3D anomalies → `buildBuilding`/`createPolygonRoom` in engine.js; auth failures → `get_current_user` + the three token-attachment paths; save weirdness → `/projects/save` full-replace semantics.

---

*This document reflects the repository exactly as it existed on branch `main`, latest commit `eba07ea`, at the time of analysis. No files in the repository were modified to produce it.*
