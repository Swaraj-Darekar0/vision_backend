# MEMORY FIX — Implementation Plan
**Fix 1: Generator Pattern | Fix 2: Frame Resize**

> **Problem:** Render free tier instance crashing with OOM (used over 512MB)
> **Root Cause:** Pose pipeline loading all video frames into RAM simultaneously + full-resolution frames fed into MediaPipe
> **Files Affected:** `pose/frame_extractor.py`, `pose/landmark_extractor.py`, `pose/pipeline.py`, `config.py`
> **All other files:** Unchanged

---

## 1. What Is Changing and Why

### Current behaviour (broken)

The frame extractor reads every frame from the video file and appends them all into a Python list before any processing begins. This means for a 62-second video at 30fps (~1860 frames), all 1860 frames — each a full-resolution numpy array — sit in memory simultaneously while MediaPipe processes them one by one.

Additionally, frames are passed to MediaPipe at their original recording resolution (likely 720p or 1080p). MediaPipe's pose model does not need this resolution to detect landmarks accurately, but it still pays the full CPU and memory cost of processing large images.

### Target behaviour (fixed)

- `frame_extractor.py` becomes a **generator** — it yields one frame at a time and the previous frame is discarded from memory before the next one is loaded.
- Frames are **resized to 640x360** inside `frame_extractor.py` before being yielded — so every downstream stage (landmark extractor, normalizer, metrics) only ever sees small frames.
- `landmark_extractor.py` is updated to **consume a generator** instead of a list.
- `pose/pipeline.py` is updated so the frame generator is passed directly into the landmark extractor without being materialised into a list first.
- A new constant `FRAME_RESIZE_WIDTH` and `FRAME_RESIZE_HEIGHT` is added to `config.py`.

---

## 2. Data Contract Change

The **shape of data** passing between stages does not change. The only change is that `frame_extractor` now returns a **generator** instead of a **list**. Every dict it yields has the exact same structure as before.

```
# Before — frame_extractor returned:
List[Dict]:  { "frame": np.ndarray,  "timestamp": float }

# After — frame_extractor returns:
Generator[Dict]:  { "frame": np.ndarray (resized to 640x360),  "timestamp": float }
```

`landmark_extractor.py` receives this generator and iterates over it with a `for` loop — which works identically whether the input is a list or a generator. No other downstream contract changes.

---

## 3. Changes by File

---

### 3.1 `config.py`

**What to add:** Two new constants for the target frame dimensions.

Add the following two constants to `config.py` in the video/frame processing section:

```python
# Frame resize dimensions — used in frame_extractor.py before MediaPipe processing
# MediaPipe pose detection does not require full resolution
# Resizing reduces both RAM usage and per-frame CPU cost on constrained hardware
FRAME_RESIZE_WIDTH  = 640
FRAME_RESIZE_HEIGHT = 360
```

> **Rule:** These values must live in `config.py` and be imported by name in `frame_extractor.py`. Do not hardcode `640` or `360` directly in the extractor.

---

### 3.2 `pose/frame_extractor.py`

This is the primary file being changed. Two things happen here:

**Change 1 — Convert from list-builder to generator**

The function must stop appending frames to a list and start using `yield` instead. The `cap.release()` call must still happen — place it after the loop, or use a `try/finally` block to guarantee it runs even if the generator is not fully consumed.

**Change 2 — Resize each frame before yielding**

After reading each frame with `cap.read()`, resize it using `cv2.resize()` before yielding. Import `FRAME_RESIZE_WIDTH` and `FRAME_RESIZE_HEIGHT` from `config.py`.

**The function signature does not change.** It still accepts `video_path: str`. The return type annotation changes from `List[Dict]` to `Generator[Dict, None, None]` (import `Generator` from `typing`).

**Behaviour rules that must be preserved:**
- Skip and do not yield frames where `ret` is `False`
- Timestamp is still extracted from `cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0` before resize (resize does not affect timestamp)
- Frame is converted to RGB (`cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`) before yielding — resize can happen before or after this conversion, either order is fine
- `cap.release()` must always be called — use `try/finally` to guarantee this

**Pseudocode (do not copy literally — adapt to your existing code style):**

```
function extract_frames(video_path):
    open video with cv2.VideoCapture
    try:
        while video is open:
            read next frame
            if read failed: break
            resize frame to (FRAME_RESIZE_WIDTH, FRAME_RESIZE_HEIGHT)
            convert frame BGR → RGB
            yield { "frame": resized_rgb_frame, "timestamp": current_timestamp }
    finally:
        release video capture
```

---

### 3.3 `pose/landmark_extractor.py`

**What to change:** The function that receives frames from `frame_extractor` must accept a generator, not just a list.

In Python, iterating over a generator and iterating over a list use identical syntax (`for item in source`). If your landmark extractor already uses a `for` loop to iterate over the frames input, **it will work without modification**.

**Check for these patterns that would break with a generator:**

- `len(frames)` — generators have no length. If this is used anywhere (e.g. for progress logging or pre-allocating arrays), replace it with a counter variable that increments inside the loop.
- `frames[i]` — index access does not work on generators. If any index-based access exists, refactor to sequential iteration.
- Iterating over `frames` more than once — a generator can only be consumed once. If the frames input is iterated over multiple times in the landmark extractor, this must be restructured so a single pass handles everything.

**Type annotation update:** Change the input parameter type hint from `List[Dict]` to `Iterable[Dict]` (import `Iterable` from `typing`). This makes the contract accurate and works for both lists and generators.

---

### 3.4 `pose/pipeline.py`

**What to change:** The orchestrator must pass the generator directly into the landmark extractor without collecting it into a list first.

**The one line that must NOT exist:**

```python
# ❌ This defeats the entire purpose of the generator — do not do this
frames = list(extract_frames(video_path))
landmark_data = extract_landmarks(frames)
```

Calling `list()` on a generator materialises the entire sequence into memory, which is exactly what we are trying to avoid.

**What it should look like instead:**

```python
# ✅ Generator is passed directly — frames flow through one at a time
frames_generator = extract_frames(video_path)
landmark_data = extract_landmarks(frames_generator)
```

No other changes to `pipeline.py` are needed. The rest of the pipeline (normalizer, metrics, aggregator, derived_attributes, json_builder) operates on `landmark_data` which is a list of landmark dicts — this is unchanged.

---

## 4. Files That Must NOT Be Modified

| File | Reason |
|---|---|
| `pose/normalizer.py` | Receives landmark dicts — unchanged |
| `pose/metrics.py` | Receives normalized landmark dicts — unchanged |
| `pose/aggregator.py` | Receives per-frame metric dicts — unchanged |
| `pose/derived_attributes.py` | Receives session-level scores — unchanged |
| `pose/json_builder.py` | Receives final score dict — unchanged |
| `pose/routes.py` | No frame handling here — unchanged |
| All `audio/` files | Audio pipeline is unaffected |
| All `evaluation/` files | Evaluation pipeline is unaffected |

---

## 5. Implementation Checklist

Use this to verify every change is correctly applied before deploying.

**config.py**
- [ ] `FRAME_RESIZE_WIDTH = 640` added
- [ ] `FRAME_RESIZE_HEIGHT = 360` added

**pose/frame_extractor.py**
- [ ] Function uses `yield` instead of `list.append()`
- [ ] No `return frames` at the end — generator functions do not return a list
- [ ] `cv2.resize(frame, (FRAME_RESIZE_WIDTH, FRAME_RESIZE_HEIGHT))` applied to every frame
- [ ] `FRAME_RESIZE_WIDTH` and `FRAME_RESIZE_HEIGHT` imported from `config` — not hardcoded
- [ ] `cap.release()` is inside a `finally` block — guaranteed to run
- [ ] Timestamp is still extracted correctly (before or after resize — both are fine)
- [ ] BGR → RGB conversion still happens before yielding
- [ ] Return type annotation updated to `Generator[Dict, None, None]`

**pose/landmark_extractor.py**
- [ ] No `len(frames)` call — replaced with counter if needed
- [ ] No index access `frames[i]` — sequential iteration only
- [ ] Frames input is only iterated once
- [ ] Input parameter type hint updated to `Iterable[Dict]`

**pose/pipeline.py**
- [ ] `list(extract_frames(...))` does NOT appear anywhere
- [ ] Generator from `extract_frames()` is passed directly into `extract_landmarks()`

---

## 6. Expected Outcome After These Changes

| Metric | Before | After |
|---|---|---|
| Peak RAM during pose pipeline | ~400–500MB (spike) | ~150–200MB (flat) |
| Frames in memory simultaneously | All (~1860 for 62s video) | 1 at a time |
| MediaPipe input resolution | 720p / 1080p | 640x360 |
| Per-frame MediaPipe processing time | Higher (large image) | Lower (small image) |
| Pose landmark accuracy | Same | Same — sufficient for body pose scoring |
| Data contracts downstream | Unchanged | Unchanged |
| Risk of OOM crash on Render | High | None under normal operation |

---

*Plan version 1.0 | Scope: pose/frame_extractor.py, pose/landmark_extractor.py, pose/pipeline.py, config.py | No other files modified.*