# Testing The Current Backend

This file reflects the current backend architecture:

- `POST /analyze/full` now supports the device-offload contract:
  - `pose_json`
  - `audio_acoustic_json`
  - `audio`
- legacy `pose_landmarks` fallback is still supported during rollout
- all heavy analysis endpoints are async and return a `job_id`

Use a strong public-speaking sample where:

- the pose JSON was generated on device from that same recording
- the acoustic JSON was generated on device from that same recording
- the speech is clean and mostly uninterrupted

## 1. Start The Server

```powershell
$env:ASSEMBLYAI_API_KEY="your_aai_key"
$env:GROQ_API_KEY="your_groq_key"
$env:SUPABASE_URL="your_supabase_url"
$env:SUPABASE_KEY="your_supabase_key"
$env:SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"
python app.py
```

## 2. Health Check

```bash
curl http://127.0.0.1:5000/health
```

## 3. Full Pipeline Test

Replace these placeholders before running:

- `test/strong_pose.json`
- `test/strong_audio_acoustic.json`
- `test/strong_audio.mp3`
- `YOUR_USER_ID`

### Start Full Analysis

```bash
curl -X POST "http://127.0.0.1:5000/analyze/full" ^
  -F "pose_json=@test/strong_pose.json;type=application/json" ^
  -F "audio_acoustic_json=@test/strong_audio_acoustic.json;type=application/json" ^
  -F "audio=@test/strong_audio.mp3;type=audio/mpeg" ^
  -F "user_id=YOUR_USER_ID" ^
  -F "topic_title=How leaders build healthy team culture" ^
  -F "duration_label=2 min" ^
  -F "is_first_session=true" ^
  -F "is_diagnostic=false" ^
  -F "speaker_level=competent"
```

Expected response:

```json
{"job_id":"...","session_id":"..."}
```

If you send `audio_acoustic_json`, do not send an MP4 on this new path. The backend now expects a compressed audio artifact such as `.mp3`.

### Poll Full Analysis Status

Replace `YOUR_JOB_ID` with the returned `job_id`.

```bash
curl "http://127.0.0.1:5000/analyze/status/YOUR_JOB_ID"
```

Poll until:

- `"status":"done"` to inspect the final result
- or `"status":"error"` to inspect the failure reason

## 4. Evaluation-Only Test

Use this when you already have `pose_json` and `audio_json` saved locally and want to test only the evaluation layer.

Create `tmp/eval_payload.json` with this shape:

```json
{
  "pose_json": {},
  "audio_json": {},
  "user_id": "YOUR_USER_ID",
  "topic_title": "How leaders build healthy team culture",
  "duration_label": "2 min",
  "is_first_session": true,
  "is_diagnostic": false,
  "speaker_level": "competent"
}
```

### Start Evaluation Job

```bash
curl -X POST "http://127.0.0.1:5000/evaluate" ^
  -H "Content-Type: application/json" ^
  --data "@tmp/eval_payload.json"
```

### Poll Evaluation Status

```bash
curl "http://127.0.0.1:5000/evaluate/status/YOUR_JOB_ID"
```

## 5. Auth Commands

### Signup

```bash
curl -X POST "http://127.0.0.1:5000/auth/signup" ^
  -H "Content-Type: application/json" ^
  --data "{\"email\":\"test@example.com\",\"password\":\"password123\"}"
```

### Login

```bash
curl -X POST "http://127.0.0.1:5000/auth/login" ^
  -H "Content-Type: application/json" ^
  --data "{\"email\":\"test@example.com\",\"password\":\"password123\"}"
```

Use the returned `user_id` in the full-pipeline and evaluation commands above.

## 6. What A Good Result Should Look Like

For a genuinely good presentation sample, the final `/analyze/full` result should usually show:

- relatively high `overall_scores.confidence`
- relatively high `overall_scores.clarity`
- low-to-moderate `overall_scores.nervousness`
- a strong `llm_feedback.topical_relevance_analysis`
- timestamped moments that are specific and grounded in the transcript and detected events

If you want a stricter benchmark, test 3 clips:

- one clearly strong speaker
- one average speaker
- one clearly weak or nervous speaker

That makes it much easier to judge whether the ranking and coaching output feel believable.

## 7. Legacy Fallback Test

Older mobile builds can still call the backend with `pose_landmarks` instead of `pose_json`.

```bash
curl -X POST "http://127.0.0.1:5000/analyze/full" ^
  -F "pose_landmarks=@test/strong_pose_landmarks.json;type=application/json" ^
  -F "audio=@test/strong_audio.mp4" ^
  -F "user_id=YOUR_USER_ID"
```
