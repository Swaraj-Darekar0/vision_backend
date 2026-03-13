# Public Speaking Coach App — Backend Project Overview

This is the Python/Flask backend for a mobile application that provides automated coaching for public speaking. It analyzes video and audio recordings to compute metrics on posture, gestures, speech patterns, and delivery quality.

## 🏗️ Architecture & Pipelines

The backend is structured into three deterministic processing pipelines that flow into a final LLM-based interpretation layer.

### 1. Pose (Video) Pipeline (`/pose`)
- **Purpose:** Analyzes body language and physical presence.
- **Input:** MP4 video file.
- **Stages:** Frame extraction (OpenCV) → Landmark extraction (MediaPipe) → Normalization → Metric computation (10 metrics) → Aggregation → Derived attributes.
- **Output:** `pose.json` containing normalized posture scores [0, 1].

### 2. Audio (Speech) Pipeline (`/audio`)
- **Purpose:** Analyzes speech acoustics, timing, and linguistic fillers.
- **Input:** Audio file or MP4 video.
- **Stages:** Preprocessing → Transcription (AssemblyAI Universal-3 Pro) → Filler detection → Acoustic feature extraction (Librosa) → Timing metrics → Event detection.
- **Output:** `audio.json` containing acoustic metrics, fillers, and timestamped events.

### 3. Final Evaluation Engine (`/evaluation`)
- **Purpose:** Fuses pose and audio data, compares with historical baselines, and generates coaching feedback.
- **Stages:** Score fusion (weighted averages) → History fetch (Supabase) → Delta computation → Write-back → LLM interpretation (Groq/GPT-4o-mini).
- **Output:** Final JSON response with overall scores, progress deltas, and human-readable coaching.

### 4. Orchestrator (`/orchestrator`)
- **Purpose:** Provides a single entry point for a "full" analysis.
- **Behavior:** Runs the Pose and Audio pipelines in **parallel** using a ThreadPoolExecutor to minimize latency before triggering the Evaluation engine.

### 5. Auth (`/auth`)
- **Purpose:** Manages user authentication (signup/login) via Supabase Auth.

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|------------|
| **Framework** | Flask 3.x (Blueprint pattern) |
| **Video/Pose** | MediaPipe 0.10+, OpenCV 4.x, NumPy, SciPy |
| **Audio/Speech** | AssemblyAI (Universal-3 Pro), Librosa 0.10+, SoundFile, PyDub |
| **Database** | Supabase (PostgreSQL) via `supabase-py` |
| **LLM Inference** | Groq (`openai/gpt-oss-20b`) |
| **Utilities** | `python-dotenv`, `concurrent.futures`, `uuid` |

---

## 📜 Development & Engineering Standards

### 1. The Three Laws of Modularity
- **Vertical Isolation:** A stage file (e.g., `metrics.py`) must never import from its orchestrator (`pipeline.py`) or a later stage. Data flows downward only.
- **Horizontal Isolation:** Files inside `pose/` must never import from `audio/` or `evaluation/`. Each package is a standalone sibling.
- **Statelessness:** No module-level variables should be written to during request processing. All state must live in local variables passed between functions.

### 2. The Single Source of Truth
- **Magic Numbers:** NO magic numbers are allowed in source code. All thresholds, weights, and constants must be imported from `config.py`.
- **Formulas:** All mathematical formulas must match the definitions in `reference_documents/master_formula.md`.
- **Clamping:** Every metric and score MUST be clamped to `[0.0, 1.0]` using `float(np.clip(val, 0.0, 1.0))` before being returned.

### 3. Database & LLM Safety
- **Write-Before-Read:** Session scores must be written to Supabase **BEFORE** the LLM call in `evaluation/pipeline.py`.
- **LLM Role:** The LLM is **read-only**. It must never compute, recalculate, or modify any numeric value. It only generates natural language feedback based on provided numbers.

---

## 🚀 Building and Running

### Prerequisites
- Python 3.10+
- FFmpeg installed on the system (required by PyDub/Librosa)
- `.env` file with API keys for AssemblyAI, Supabase, and Groq.

### Installation
```bash
pip install -r requirements.txt
```

### Running the Server
```bash
python app.py
```
The server starts on `http://localhost:5000`.

### Key Endpoints
- `POST /analyze/full`: Upload a video for complete parallel analysis.
- `POST /pose/analyze`: Video analysis only.
- `POST /audio/analyze`: Audio/Video analysis for speech only.
- `POST /evaluate`: Fuse results and generate coaching (requires existing JSONs).
- `POST /auth/signup` / `POST /auth/login`: User management.

---

## 📂 Canonical File Structure
```
backend/
├── app.py                # Flask factory and registration
├── config.py             # ALL numeric constants and API settings
├── pose/                 # Pipeline 1: Video/Pose logic
├── audio/                # Pipeline 2: Audio/Speech logic
├── evaluation/           # Pipeline 3: Fusion and LLM logic
├── orchestrator/         # Parallel execution of pipelines
├── auth/                 # Authentication logic
├── reference_documents/  # Master formulas and implementation plan
├── tmp/                  # Temporary file processing (autocreated)
└── test/                 # Test assets and scripts
```
