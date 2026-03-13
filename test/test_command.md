# Testing the Backend Pipelines

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

### 3. Analyze Pose (Video)
```bash
curl -X POST -F "video=@testVideo(Long).mp4" http://127.0.0.1:5000/pose/analyze
```

### 4. Analyze Audio (Audio/Video)
```bash
curl -X POST -F "audio=@testVideo(Long).mp4" http://127.0.0.1:5000/audio/analyze
```

### 5. Final Evaluation
curl -X POST -H "Content-Type: application/json" -d @tmp\eval.json http://127.0.0.1:5000/evaluate 

### 6. User Authentication

#### Signup
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/auth/signup" -Method Post -ContentType "application/json" -Body '{"email": "test@example.com", "password": "password123"}'
```

#### Login
```bash
Invoke-RestMethod -Uri "http://127.0.0.1:5000/auth/login" -Method Post -ContentType "application/json" -Body '{"email": "test@example.com", "password": "password123"}'
```
**Note:** Use the `user_id` (UUID) returned from login in your `eval_payload.json` or evaluation request. The database now requires a valid UUID linked to a user profile.

### 7. Full Analysis (Orchestrator)
This runs Pose, Audio, and Evaluation pipelines in one go.
Requires `user_id` from step 6 (Login).

```bash
curl -X POST -F "video=@testVideo(Long).mp4" -F "user_id=0f48f97b-03d3-4394-a9af-f8b2d91ce94c" http://127.0.0.1:5000/analyze/full
```
