import os
import time
import fitz
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException
from app.services.vision.pipeline import process_image

router = APIRouter(prefix="/upload", tags=["upload"])

from fastapi.responses import StreamingResponse
import json
import asyncio
import concurrent.futures

@router.post("")
async def upload_files(files: List[UploadFile] = File(...)):
    os.makedirs("uploads", exist_ok=True)
    
    file_data = []
    for f in files:
        contents = await f.read()
        file_data.append((f.filename, contents))

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        
        def background_worker(file_idx, filename, contents):
            try:
                if filename.lower().endswith(".pdf"):
                    doc = fitz.open(stream=contents, filetype="pdf")
                    if len(doc) == 0: return
                    for page_idx in range(len(doc)):
                        page = doc.load_page(page_idx)
                        zoom = 150 / 72.0
                        page_rect = page.rect
                        max_dim_pixels = max(page_rect.width, page_rect.height) * zoom
                        if max_dim_pixels > 2000.0:
                            zoom = zoom * (2000.0 / max_dim_pixels)
                        mat = fitz.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=mat)
                        img_bytes = pix.tobytes("png")
                        fname = f"floor_pdf_{file_idx}_{page_idx}_{int(time.time()*1000)}.png"
                        fpath = f"uploads/{fname}"
                        with open(fpath, "wb") as f:
                            f.write(img_bytes)
                            
                        final_res = None
                        for step in process_image(img_bytes):
                            if isinstance(step, tuple):
                                pct, msg = step
                                asyncio.run_coroutine_threadsafe(queue.put(("progress", file_idx, pct, f"[{filename}] {msg}")), loop)
                            else:
                                final_res = step
                        if final_res:
                            asyncio.run_coroutine_threadsafe(queue.put(("result", file_idx, final_res, fpath)), loop)
                            if len(final_res["walls"]) > 0 or len(final_res["rooms"]) > 0:
                                break
                else:
                    fname = f"floor_img_{file_idx}_{int(time.time()*1000)}.png"
                    fpath = f"uploads/{fname}"
                    with open(fpath, "wb") as f:
                        f.write(contents)
                    for step in process_image(contents):
                        if isinstance(step, tuple):
                            pct, msg = step
                            asyncio.run_coroutine_threadsafe(queue.put(("progress", file_idx, pct, f"[{filename}] {msg}")), loop)
                        else:
                            asyncio.run_coroutine_threadsafe(queue.put(("result", file_idx, step, fpath)), loop)
            except Exception as e:
                import traceback
                print(f"[ERROR] processing {filename}: {traceback.format_exc()}")
                asyncio.run_coroutine_threadsafe(queue.put(("error", file_idx, str(e), None)), loop)

        yield f"data: {json.dumps({'status': 'progress', 'progress': 0, 'message': f'Initializing concurrent upload for {len(file_data)} files...'})}\n\n"

        async def run_all():
            max_workers = max(1, min(10, len(file_data)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = []
                for idx, (fname, contents) in enumerate(file_data):
                    futures.append(loop.run_in_executor(pool, background_worker, idx, fname, contents))
                await asyncio.gather(*futures)
            await queue.put(("DONE", None, None, None))
            
        asyncio.create_task(run_all())
        
        results = {}
        errors = []
        progress_map = {i: 0 for i in range(len(file_data))}
        
        while True:
            msg_type, file_idx, payload, extra = await queue.get()
            if msg_type == "DONE":
                break
            elif msg_type == "progress":
                progress_map[file_idx] = payload
                # Average progress across all files
                avg_pct = sum(progress_map.values()) // len(progress_map)
                yield f"data: {json.dumps({'status': 'progress', 'progress': avg_pct, 'message': extra})}\n\n"
            elif msg_type == "result":
                results[file_idx] = {
                    "walls": payload["walls"], "rooms": payload["rooms"],
                    "doors": payload.get("doors", []),
                    "imageUrl": f"/{extra}?t={time.time()}",
                    "width": payload["width"], "height": payload["height"],
                }
            elif msg_type == "error":
                errors.append(f"File {file_idx}: {payload}")
                
        if not results and errors:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to process floors. Errors: {errors}'})}\n\n"
            return
            
        final_list = [results[i] for i in range(len(file_data)) if i in results]
        yield f"data: {json.dumps({'status': 'success', 'data': {'floors': final_list}})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/save-image")
async def save_image(file: UploadFile = File(...)):
    """Save a pre-processed image without running the vision pipeline."""
    os.makedirs("uploads", exist_ok=True)
    contents = await file.read()
    fname = f"floor_rotated_{int(time.time()*1000)}.png"
    fpath = f"uploads/{fname}"
    with open(fpath, "wb") as f:
        f.write(contents)
    return {"imageUrl": f"/{fpath}?t={time.time()}"}
