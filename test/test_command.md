# Testing the Backend Pipelines (Async Update)

**Note:** All analysis endpoints now return immediately with a `job_id`. You must poll the status endpoint to get the result.

### 0. Download MediaPipe Model
The new MediaPipe Tasks API requires a model file. Download the "Full" pose model:
```bash
curl -o pose_landmarker_full.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
```

### 1. Start the Server
Set your API keys before starting:
```powershell
$env:ASSEMBLYAI_API_KEY="your_aai_key"
$env:GROQ_API_KEY="your_groq_key"
python app.py
```

### 2. Health Check
```bash
curl http://127.0.0.1:5000/health
```

### 3. Analyze Pose (Video) - Async
**Step 1: Start Job**
```bash
# Returns {"job_id": "...", "session_id": "..."}
$response = Invoke-RestMethod -Uri "http://127.0.0.1:5000/pose/analyze" -Method Post -InFile "testVideo(Long).mp4" -ContentType "multipart/form-data"
$jobId = $response.job_id
Write-Host "Job ID: $jobId"
```

**Step 2: Poll Status**
```bash
# Repeat until status is "done"
Invoke-RestMethod -Uri "http://127.0.0.1:5000/pose/status/$jobId" -Method Get
```

### 4. Analyze Audio (Audio/Video) - Async
**Step 1: Start Job**
```bash
$response = Invoke-RestMethod -Uri "http://127.0.0.1:5000/audio/analyze" -Method Post -InFile "testVideo(Long).mp4" -ContentType "multipart/form-data"
$jobId = $response.job_id
```

**Step 2: Poll Status**
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/audio/status/$jobId" -Method Get
```

### 5. Final Evaluation - Async
**Step 1: Start Job**
```bash
$response = Invoke-RestMethod -Uri "http://127.0.0.1:5000/evaluate" -Method Post -ContentType "application/json" -InFile "tmp\eval.json"
$jobId = $response.job_id
```

**Step 2: Poll Status**
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/evaluate/status/$jobId" -Method Get
```

### 6. User Authentication (Synchronous)

#### Signup
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/auth/signup" -Method Post -ContentType "application/json" -Body '{"email": "test@example.com", "password": "password123"}'
```

#### Login
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/auth/login" -Method Post -ContentType "application/json" -Body '{"email": "test@example.com", "password": "password123"}'
```
**Note:** Use the `user_id` (UUID) returned from login in your `eval_payload.json` or evaluation request. The database now requires a valid UUID linked to a user profile.

### 7. Full Analysis (Orchestrator) - Async
This runs Pose, Audio, and Evaluation pipelines in one go.
Requires `user_id` from step 6 (Login).

**Step 1: Start Job**
```bash
$response = Invoke-RestMethod -Uri "http://127.0.0.1:5000/analyze/full" -Method Post -ContentType "multipart/form-data" -Body @{ video = Get-Item "test_video.mp4"; user_id = "0f48f97b-03d3-4394-a9af-f8b2d91ce94c" }
$jobId = $response.job_id
```

**Step 2: Poll Status**
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/analyze/status/$jobId" -Method Get
```
