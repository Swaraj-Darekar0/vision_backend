# Pose Architecture Migration — Implementation Guide
**Shift: Backend MediaPipe → On-Device BlazePose (TF.js React Native)**

> **Document Type:** Developer Implementation Instructions
> **Scope:** Frontend (React Native) + Backend (Python/Flask)
> **Purpose:** Migrate pose landmark extraction from the backend to the mobile device using BlazePose via TF.js React Native, so the backend receives pre-extracted numerical landmark data instead of a raw video file.
> **Backend Impact:** `frame_extractor.py` and `landmark_extractor.py` are fully retired. Pipeline starts at `normalizer.py`.
> **Frontend Impact:** BlazePose runs in real-time during recording. Landmark arrays replace video file as the pose payload.

---

## Table of Contents

1. [Architecture Before vs After](#1-architecture-before-vs-after)
2. [New Data Contract (Shared — Both Developers Must Read)](#2-new-data-contract-shared--both-developers-must-read)
3. [Frontend Developer Instructions](#3-frontend-developer-instructions)
4. [Backend Developer Instructions](#4-backend-developer-instructions)
5. [Integration Checklist](#5-integration-checklist)
6. [Error Handling Contract](#6-error-handling-contract)
7. [Testing Instructions](#7-testing-instructions)

---

## 1. Architecture Before vs After

### Before (Current)

```
Mobile Device
    │
    ├─ Records video (MP4)
    ├─ Compresses to 480p (~9MB for 1 min)
    └─ Uploads compressed MP4 to backend
            │
            ▼
Backend — POST /analyze/full
    ├─ frame_extractor.py      ← OpenCV reads MP4, yields frames
    ├─ landmark_extractor.py   ← MediaPipe runs on each frame → (33, 4) arrays
    ├─ normalizer.py
    ├─ metrics.py
    ├─ aggregator.py
    ├─ derived_attributes.py
    └─ json_builder.py
```

**Problems with current approach:**
- Video upload: ~9MB per 1-minute session on slow connections
- Backend RAM: All frames loaded simultaneously → OOM crashes on Render free tier
- Backend time: Frame extraction + MediaPipe inference = 53–105s of the total processing time
- User wait after stopping: 2.5–4 minutes on average 4G

---

### After (Target)

```
Mobile Device — During Recording (parallel, zero extra user wait)
    │
    ├─ VisionCamera → raw frame buffer
    ├─ BlazePose (TF.js) → 33 keypoints per frame → buffered with timestamp
    └─ expo-av → audio recorded in parallel
            │
            ▼ (user taps Stop)
    ├─ Serialize landmark buffer → JSON (~2.5–5MB)
    ├─ Finalize audio file (~0.5MB)
    └─ Upload: landmark JSON + audio file to backend
            │
            ▼
Backend — POST /analyze/full (new version)
    ├─ ❌ frame_extractor.py      RETIRED
    ├─ ❌ landmark_extractor.py   RETIRED
    ├─ normalizer.py              ← receives landmark JSON directly
    ├─ metrics.py
    ├─ aggregator.py
    ├─ derived_attributes.py
    └─ json_builder.py
```

**Gains from new approach:**
- Upload payload: ~3–5.5MB total (60–70% reduction)
- Backend skips its two most expensive stages
- User wait after stopping: ~45–85s on average 4G (60–75% faster)
- Backend RAM: No video frames in memory — OOM problem eliminated

---

## 2. New Data Contract (Shared — Both Developers Must Read)

This section defines the exact JSON structure the frontend sends and the backend receives for pose data. Both developers must implement against this contract precisely. Do not deviate from field names, types, or structure.

### 2.1 Pose Payload — Frontend Sends, Backend Receives

```json
{
  "session_id": "uuid-string",
  "user_id": "uuid-string",
  "fps_achieved": 22.4,
  "total_frames": 1344,
  "duration_seconds": 60.0,
  "frames": [
    {
      "timestamp": 0.000,
      "landmarks": [
        { "x": 0.512, "y": 0.234, "z": -0.041, "visibility": 0.98 },
        { "x": 0.498, "y": 0.198, "z": -0.038, "visibility": 0.96 },
        // ... 33 total landmarks, indices 0–32
        // Index order matches MediaPipe / BlazePose standard schema
      ]
    },
    {
      "timestamp": 0.044,
      "landmarks": [ /* 33 landmarks */ ]
    }
    // ... one entry per captured frame for the full session duration
  ]
}
```

### 2.2 Landmark Index Reference (BlazePose 33-Point Schema)

This is the canonical landmark index mapping. Both frontend (buffering) and backend (metrics.py landmark constants) must agree on these indices. They are identical to the MediaPipe Pose schema — no remapping required.

| Index | Name | Used In Your Metrics |
|---|---|---|
| 0 | nose | head_stability |
| 11 | left_shoulder | shoulder_alignment, spine_straightness, posture_openness, symmetry |
| 12 | right_shoulder | shoulder_alignment, spine_straightness, posture_openness, symmetry |
| 13 | left_elbow | gesture_score, amplitude_score |
| 14 | right_elbow | gesture_score, amplitude_score |
| 15 | left_wrist | gesture_score, amplitude_score, fidget_score, stillness_score |
| 16 | right_wrist | gesture_score, amplitude_score, fidget_score, stillness_score |
| 23 | left_hip | normalizer anchor, spine_straightness, body_sway, symmetry |
| 24 | right_hip | normalizer anchor, spine_straightness, body_sway, symmetry |

All 33 landmarks must be included in every frame even if not directly used in metrics. Do not send partial landmark arrays.

### 2.3 Field Definitions

| Field | Type | Description |
|---|---|---|
| `session_id` | string (UUID) | Generated by frontend at recording start. Same ID used for audio upload. |
| `user_id` | string (UUID) | From Supabase auth. Same as current implementation. |
| `fps_achieved` | float | Actual average FPS achieved during BlazePose inference. Backend uses this for validation only. |
| `total_frames` | int | Total number of frames in the `frames` array. |
| `duration_seconds` | float | Total recording duration in seconds. |
| `frames[].timestamp` | float | Seconds from recording start. Must be monotonically increasing. First frame = 0.000. |
| `frames[].landmarks` | array[33] | Exactly 33 landmark objects in index order 0–32. |
| `landmarks[].x` | float [0.0–1.0] | Normalized horizontal position. 0 = left edge, 1 = right edge of frame. |
| `landmarks[].y` | float [0.0–1.0] | Normalized vertical position. 0 = top edge, 1 = bottom edge of frame. |
| `landmarks[].z` | float | Depth relative to hip midpoint. Negative = closer to camera. Not clamped. |
| `landmarks[].visibility` | float [0.0–1.0] | Model confidence that landmark is visible. Below 0.5 = unreliable. |

### 2.4 Multipart Upload Structure

The frontend sends a single `multipart/form-data` POST to `/analyze/full` containing:

| Field Name | Content | Type |
|---|---|---|
| `pose_landmarks` | Landmark JSON (described above) | `application/json` as file |
| `audio` | Audio file (AAC or WAV) | `audio/aac` or `audio/wav` |
| `user_id` | UUID string | `text/plain` |
| `session_id` | UUID string | `text/plain` |

---

## 3. Frontend Developer Instructions

> **Your role:** Implement real-time BlazePose inference during recording, buffer landmark arrays with timestamps, and send the landmark JSON + audio file to the backend after the user stops recording. You are replacing the video compression and video upload flow entirely for the pose component.

---

### 3.1 Package Changes

**Remove:**
```bash
# Remove react-native-compressor (video compression no longer needed for pose)
npm uninstall react-native-compressor
```

**Add:**
```bash
# Camera with frame processor support
npm install react-native-vision-camera

# TF.js runtime for React Native
npm install @tensorflow/tfjs-react-native
npm install @tensorflow/tfjs-core
npm install @tensorflow/tfjs-backend-webgl

# BlazePose model
npm install @tensorflow-models/pose-detection

# Audio recording (replaces expo-camera audio track)
npx expo install expo-av
```

**Update `app.json`:**
```json
{
  "expo": {
    "plugins": [
      ["react-native-vision-camera", {
        "cameraPermission": "SpeakingCoach uses the camera to record your presentations.",
        "microphonePermission": "SpeakingCoach uses the microphone to capture your speech."
      }]
    ]
  }
}
```

After updating `app.json`:
```bash
npx expo prebuild
# Then rebuild Dev Client:
# iOS:     npx expo run:ios
# Android: npx expo run:android
```

---

### 3.2 New File: `src/utils/blazePoseSetup.ts`

This file owns model initialization. The model must be loaded once and reused — never initialize inside a render cycle or per-frame.

```typescript
import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-react-native';
import '@tensorflow/tfjs-backend-webgl';
import * as poseDetection from '@tensorflow-models/pose-detection';

let detector: poseDetection.PoseDetector | null = null;
let isInitializing = false;

/**
 * Initializes TF.js backend and loads BlazePose model.
 * Safe to call multiple times — returns cached detector after first load.
 * Call this on app launch or on DashboardScreen mount, not on RecordingScreen mount.
 * Loading takes 3–8 seconds on first call.
 */
export async function initializeBlazePose(): Promise<poseDetection.PoseDetector> {
  if (detector) return detector;
  if (isInitializing) {
    // Wait for existing initialization to complete
    while (isInitializing) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    return detector!;
  }

  isInitializing = true;
  try {
    await tf.ready();

    detector = await poseDetection.createDetector(
      poseDetection.SupportedModels.BlazePose,
      {
        runtime: 'tfjs',
        modelType: 'full',       // 'lite' for low-end devices, 'full' for mid/high
        enableSmoothing: false,  // disabled — smoothing adds latency, we want raw values
        enableSegmentation: false,
      }
    );

    console.log('[BlazePose] Model loaded and ready');
    return detector;
  } finally {
    isInitializing = false;
  }
}

/**
 * Disposes the detector and frees GPU memory.
 * Call on app logout or if you need to free resources.
 */
export async function disposeBlazePose(): Promise<void> {
  if (detector) {
    detector.dispose();
    detector = null;
  }
}
```

---

### 3.3 New Type: `src/types/pose.ts`

```typescript
/**
 * Single landmark point — matches BlazePose output and backend input contract.
 * Index order matches MediaPipe 33-point schema exactly.
 */
export interface LandmarkPoint {
  x: number;           // [0.0–1.0] normalized horizontal
  y: number;           // [0.0–1.0] normalized vertical
  z: number;           // depth, not clamped
  visibility: number;  // [0.0–1.0] model confidence
}

/**
 * One captured frame — landmark array + timestamp.
 */
export interface LandmarkFrame {
  timestamp: number;          // seconds from recording start
  landmarks: LandmarkPoint[]; // exactly 33 points, indices 0–32
}

/**
 * Complete pose payload sent to backend.
 */
export interface PoseLandmarkPayload {
  session_id:       string;
  user_id:          string;
  fps_achieved:     number;
  total_frames:     number;
  duration_seconds: number;
  frames:           LandmarkFrame[];
}
```

---

### 3.4 New Hook: `src/hooks/useBlazePoseRecording.ts`

This hook replaces `useRecording.ts` for the pose capture component. It owns camera frame processing, landmark buffering, audio recording, and session finalization.

```typescript
import { useRef, useState, useCallback, useEffect } from 'react';
import { Camera, useCameraDevice, useFrameProcessor } from 'react-native-vision-camera';
import { useRunOnJS } from 'react-native-worklets-core';
import { Audio } from 'expo-av';
import * as tf from '@tensorflow/tfjs-core';
import * as poseDetection from '@tensorflow-models/pose-detection';
import { initializeBlazePose } from '../utils/blazePoseSetup';
import { LandmarkFrame, PoseLandmarkPayload } from '../types/pose';

export type RecordingState = 'idle' | 'recording' | 'paused' | 'stopped';

export function useBlazePoseRecording(userId: string) {
  const device = useCameraDevice('front');
  const detectorRef = useRef<poseDetection.PoseDetector | null>(null);
  const landmarkBufferRef = useRef<LandmarkFrame[]>([]);
  const recordingStartTimeRef = useRef<number>(0);
  const frameCountRef = useRef<number>(0);
  const audioRecordingRef = useRef<Audio.Recording | null>(null);

  const [state, setState] = useState<RecordingState>('idle');
  const [elapsedSeconds, setElapsed] = useState(0);
  const [isModelReady, setModelReady] = useState(false);
  const [audioUri, setAudioUri] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Model Initialization ───────────────────────────────────────────────────

  useEffect(() => {
    initializeBlazePose()
      .then((d) => {
        detectorRef.current = d;
        setModelReady(true);
      })
      .catch((err) => console.error('[BlazePose] Init failed:', err));
  }, []);

  // ─── Timer ──────────────────────────────────────────────────────────────────

  const startTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
  };

  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  // ─── Frame Processor ────────────────────────────────────────────────────────
  // Runs on every camera frame during recording.
  // CRITICAL: dispose tensors after every inference or GPU memory leaks.

  const handleLandmarkFrame = useRunOnJS(
    (landmarks: LandmarkFrame) => {
      landmarkBufferRef.current.push(landmarks);
      frameCountRef.current += 1;
    },
    []
  );

  const frameProcessor = useFrameProcessor(
    (frame) => {
      'worklet';
      if (!detectorRef.current || state !== 'recording') return;

      try {
        // Convert VisionCamera frame to tensor
        const imageTensor = tf.browser.fromPixels({
          data: new Uint8Array(frame.toArrayBuffer()),
          width: frame.width,
          height: frame.height,
        });

        // Run BlazePose inference
        const poses = detectorRef.current.estimatePoses(imageTensor, {
          flipHorizontal: true, // front camera is mirrored
        });

        // Dispose tensor immediately — critical for memory
        imageTensor.dispose();

        if (poses.length === 0 || !poses[0].keypoints3D) return;

        const pose = poses[0];
        const timestamp =
          (Date.now() - recordingStartTimeRef.current) / 1000;

        // Map BlazePose output to our LandmarkPoint contract
        const landmarks = pose.keypoints3D!.map((kp) => ({
          x: kp.x,
          y: kp.y,
          z: kp.z ?? 0,
          visibility: kp.score ?? 0,
        }));

        handleLandmarkFrame({ timestamp, landmarks });
      } catch (err) {
        // Never throw in frame processor — log and continue
        console.warn('[BlazePose] Frame inference error:', err);
      }
    },
    [state]
  );

  // ─── Audio Recording ────────────────────────────────────────────────────────

  const startAudioRecording = async () => {
    await Audio.requestPermissionsAsync();
    await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });

    const { recording } = await Audio.Recording.createAsync(
      Audio.RecordingOptionsPresets.HIGH_QUALITY
    );
    audioRecordingRef.current = recording;
  };

  const stopAudioRecording = async (): Promise<string | null> => {
    if (!audioRecordingRef.current) return null;
    await audioRecordingRef.current.stopAndUnloadAsync();
    const uri = audioRecordingRef.current.getURI();
    audioRecordingRef.current = null;
    return uri ?? null;
  };

  // ─── Recording Controls ─────────────────────────────────────────────────────

  const startRecording = useCallback(async () => {
    if (!isModelReady) {
      console.warn('[BlazePose] Model not ready yet');
      return;
    }
    landmarkBufferRef.current = [];
    frameCountRef.current = 0;
    recordingStartTimeRef.current = Date.now();
    setElapsed(0);
    setState('recording');
    startTimer();
    await startAudioRecording();
  }, [isModelReady]);

  const stopRecording = useCallback(async (): Promise<{
    landmarkPayload: PoseLandmarkPayload;
    audioUri: string | null;
  }> => {
    stopTimer();
    setState('stopped');

    const uri = await stopAudioRecording();
    setAudioUri(uri);

    const durationSeconds = elapsedSeconds;
    const frames = landmarkBufferRef.current;
    const fpsAchieved =
      durationSeconds > 0 ? frames.length / durationSeconds : 0;

    const landmarkPayload: PoseLandmarkPayload = {
      session_id:       generateSessionId(), // see src/utils below
      user_id:          userId,
      fps_achieved:     parseFloat(fpsAchieved.toFixed(2)),
      total_frames:     frames.length,
      duration_seconds: durationSeconds,
      frames,
    };

    return { landmarkPayload, audioUri: uri };
  }, [elapsedSeconds, userId]);

  const pauseRecording = useCallback(() => {
    stopTimer();
    setState('paused');
  }, []);

  const resumeRecording = useCallback(() => {
    setState('recording');
    startTimer();
  }, []);

  return {
    device,
    frameProcessor,
    state,
    elapsedSeconds,
    isModelReady,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
  };
}

function generateSessionId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
```

---

### 3.5 Update: `src/hooks/useVideoUpload.ts` → rename to `src/hooks/useSessionUpload.ts`

The upload hook no longer handles video compression. It sends landmark JSON + audio.

**Remove entirely:**
- All calls to `compressVideoFor480p()`
- The `compPct` compression progress state
- Import of `react-native-compressor`

**Replace upload logic with:**

```typescript
async function uploadSession(
  landmarkPayload: PoseLandmarkPayload,
  audioUri: string,
  topicTitle: string,
): Promise<boolean> {
  try {
    setError(null);
    setStatus('uploading');
    setUpPct(0);

    // Serialize landmark JSON to a blob
    const landmarkJson = JSON.stringify(landmarkPayload);
    const landmarkBlob = new Blob([landmarkJson], { type: 'application/json' });

    const form = new FormData();
    form.append('pose_landmarks', landmarkBlob, 'landmarks.json');
    form.append('audio', {
      uri: audioUri,
      name: 'audio.m4a',
      type: 'audio/mp4',
    } as any);
    form.append('user_id', user?.id ?? '');
    form.append('session_id', landmarkPayload.session_id);

    const response = await apiClient.post<EvaluationResult>(
      ENDPOINTS.analyzeFullVideo,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) {
            const pct = Math.round((evt.loaded / evt.total) * 100);
            setUpPct(pct);
            if (pct >= 100) setStatus('processing');
          }
        },
      }
    );

    const result = response.data;
    await saveSession(result, landmarkPayload.duration_seconds, topicTitle);
    setLatestResult(result);
    setStatus('done');
    return true;
  } catch (err: any) {
    setStatus('error');
    setError(err?.response?.data?.error ?? err?.message ?? 'Upload failed');
    return false;
  }
}
```

---

### 3.6 Update: `RecordingScreen.tsx`

Replace `CameraView` from `expo-camera` with `Camera` from `react-native-vision-camera`. Replace `useRecording` hook with `useBlazePoseRecording`.

**Key changes:**

```typescript
// REMOVE
import { CameraView } from 'expo-camera';
import { useRecording } from '../hooks/useRecording';

// ADD
import { Camera } from 'react-native-vision-camera';
import { useBlazePoseRecording } from '../hooks/useBlazePoseRecording';
```

```typescript
// REMOVE — video URI watch effect
useEffect(() => {
  if (state === 'stopped' && videoUri) {
    navigation.replace('Processing', { videoUri });
  }
}, [state, videoUri]);

// ADD — landmark payload watch
const handleStop = async () => {
  const { landmarkPayload, audioUri } = await stopRecording();
  setRecordingMeta(landmarkPayload.duration_seconds, topicTitle);
  navigation.replace('Processing', {
    landmarkPayload,
    audioUri,
  });
};
```

```typescript
// Camera component usage
<Camera
  ref={cameraRef}
  style={StyleSheet.absoluteFill}
  device={device}
  isActive={state === 'recording' || state === 'paused'}
  frameProcessor={frameProcessor}
  frameProcessorFps={30}  // attempts 30fps, device may achieve less
/>
```

---

### 3.7 Update: Navigation Types `src/types/navigation.ts`

```typescript
// REMOVE
Processing: { videoUri: string };

// ADD
Processing: {
  landmarkPayload: PoseLandmarkPayload;
  audioUri: string;
};
```

---

### 3.8 Update: `ProcessingScreen.tsx`

```typescript
// REMOVE sub-state: 'compressing'
// REMOVE compPct display
// REMOVE "Optimising Video" UI state

// UPDATE — sub-states are now:
// 'uploading' → 'processing' → 'done' | 'error'

// UPDATE status label map:
const STATUS_LABELS = {
  uploading:  { title: 'Uploading Session',      subtitle: `${upPct}% uploaded` },
  processing: { title: 'Analysing Your Session', subtitle: 'Detecting pose & speech...' },
  error:      { title: 'Something went wrong',   subtitle: error ?? '' },
};
```

---

### 3.9 Remove: `src/utils/compressVideo.ts`

Delete this file entirely. Video compression is no longer part of the flow.

---

### 3.10 Update: Model Preloading

Call `initializeBlazePose()` on app launch or `DashboardScreen` mount — not on `RecordingScreen` mount. This hides the 3–8 second cold start from the user.

```typescript
// DashboardScreen.tsx — add to useEffect on mount
useEffect(() => {
  initializeBlazePose().catch(console.error); // warm up in background
}, []);
```

---

### 3.11 Low-End Device Fallback

On devices where WebGL is unavailable, TF.js falls back to CPU automatically. You should detect which backend is active after initialization and log it:

```typescript
// In blazePoseSetup.ts, after tf.ready():
const backendName = tf.getBackend();
console.log(`[TF.js] Backend: ${backendName}`); // 'webgl' or 'cpu'

// If CPU backend: inference will be slower (200–300ms/frame → 3–5fps)
// This is acceptable — timestamps remain accurate, aggregator handles sparse frames
```

---

## 4. Backend Developer Instructions

> **Your role:** Retire `frame_extractor.py` and `landmark_extractor.py`. Update the orchestrator to accept landmark JSON from the request instead of a video file. Update the route handler for `/analyze/full`. Everything from `normalizer.py` onward is unchanged.

---

### 4.1 Files to DELETE

Remove these files entirely from the codebase. They are no longer called by anything.

```
pose/frame_extractor.py      ← DELETE
pose/landmark_extractor.py   ← DELETE
```

Remove their imports from `pose/pipeline.py`:

```python
# REMOVE these imports from pose/pipeline.py
from pose.frame_extractor import extract_frames
from pose.landmark_extractor import extract_landmarks
```

---

### 4.2 New File: `pose/landmark_parser.py`

This file replaces both deleted files. Its only job is to parse the incoming landmark JSON into the same data structure that `normalizer.py` already expects. No math, no thresholds, no MediaPipe.

```python
"""
pose/landmark_parser.py

Parses the landmark JSON payload received from the React Native frontend
(BlazePose via TF.js) into the normalized list-of-dicts format that
normalizer.py expects.

This file replaces frame_extractor.py and landmark_extractor.py entirely.
No MediaPipe, no OpenCV, no video file handling.

Input contract (from frontend):
    {
      "session_id": str,
      "user_id": str,
      "fps_achieved": float,
      "total_frames": int,
      "duration_seconds": float,
      "frames": [
        {
          "timestamp": float,
          "landmarks": [
            { "x": float, "y": float, "z": float, "visibility": float },
            ... 33 total
          ]
        },
        ...
      ]
    }

Output contract (to normalizer.py) — identical to what landmark_extractor.py produced:
    List[Dict]: {
        "landmarks": np.ndarray,  # shape (33, 4) — columns: x, y, z, visibility
        "timestamp": float,
        "valid": bool
    }
"""

import logging
import numpy as np
from typing import List, Dict, Any

from config import MIN_VISIBILITY_THRESHOLD

logger = logging.getLogger(__name__)

# Minimum number of key landmarks that must be visible for a frame to be valid.
# Uses the same threshold constant as the retired landmark_extractor.py.
_KEY_LANDMARK_INDICES = [0, 11, 12, 23, 24]  # nose, shoulders, hips


def parse_landmark_payload(payload: Dict[str, Any]) -> List[Dict]:
    """
    Converts the frontend landmark JSON payload into the list-of-dicts format
    expected by normalizer.py.

    Args:
        payload: Parsed JSON dict from the multipart request field 'pose_landmarks'.

    Returns:
        List of frame dicts with keys: landmarks (np.ndarray shape 33x4),
        timestamp (float), valid (bool).

    Raises:
        ValueError: If payload is missing required top-level fields.
    """
    if 'frames' not in payload:
        raise ValueError("Landmark payload missing required field: 'frames'")
    if not isinstance(payload['frames'], list):
        raise ValueError("Landmark payload 'frames' must be a list")

    frames = payload['frames']
    logger.info(
        f"[LandmarkParser] Parsing {len(frames)} frames "
        f"| fps_achieved={payload.get('fps_achieved', 'unknown')} "
        f"| duration={payload.get('duration_seconds', 'unknown')}s"
    )

    parsed_frames = []

    for i, frame in enumerate(frames):
        try:
            parsed = _parse_single_frame(frame, i)
            parsed_frames.append(parsed)
        except Exception as e:
            logger.warning(
                f"[LandmarkParser] Frame {i} at t={frame.get('timestamp', '?')} "
                f"failed parsing: {e} — marking invalid"
            )
            parsed_frames.append({
                "landmarks": np.zeros((33, 4), dtype=np.float32),
                "timestamp": frame.get('timestamp', 0.0),
                "valid": False,
            })

    valid_count = sum(1 for f in parsed_frames if f['valid'])
    logger.info(
        f"[LandmarkParser] {valid_count}/{len(parsed_frames)} frames valid "
        f"after parsing"
    )

    return parsed_frames


def _parse_single_frame(frame: Dict, frame_index: int) -> Dict:
    """
    Parses one frame dict from the payload into the normalizer.py input format.

    Args:
        frame: Single frame dict with 'timestamp' and 'landmarks' keys.
        frame_index: Index in the frames array (for logging only).

    Returns:
        Dict with 'landmarks' (np.ndarray 33x4), 'timestamp' (float), 'valid' (bool).
    """
    timestamp = float(frame['timestamp'])
    raw_landmarks = frame['landmarks']

    if len(raw_landmarks) != 33:
        raise ValueError(
            f"Expected 33 landmarks, got {len(raw_landmarks)}"
        )

    # Build (33, 4) numpy array — columns: x, y, z, visibility
    # This is the identical shape produced by the retired landmark_extractor.py
    landmark_array = np.array(
        [
            [
                float(lm['x']),
                float(lm['y']),
                float(lm['z']),
                float(lm['visibility']),
            ]
            for lm in raw_landmarks
        ],
        dtype=np.float32,
    )  # shape: (33, 4)

    # Validate frame using the same visibility rule as landmark_extractor.py
    key_visibilities = landmark_array[_KEY_LANDMARK_INDICES, 3]
    mean_visibility = float(np.mean(key_visibilities))
    is_valid = mean_visibility >= MIN_VISIBILITY_THRESHOLD

    if not is_valid:
        logger.warning(
            f"[LandmarkParser] Frame {frame_index} at t={timestamp:.3f}s "
            f"marked invalid — mean key landmark visibility {mean_visibility:.3f} "
            f"< threshold {MIN_VISIBILITY_THRESHOLD}"
        )

    return {
        "landmarks": landmark_array,
        "timestamp": timestamp,
        "valid": is_valid,
    }
```

---

### 4.3 Update: `pose/pipeline.py`

The orchestrator loses two stage calls and gains one parser call. All other stage calls are identical.

```python
# pose/pipeline.py

import logging
from pose.landmark_parser import parse_landmark_payload   # NEW
from pose.normalizer import normalize_landmarks
from pose.metrics import compute_all_metrics
from pose.aggregator import aggregate_windows, aggregate_session
from pose.derived_attributes import compute_derived_attributes
from pose.json_builder import build_pose_json

# REMOVED imports:
# from pose.frame_extractor import extract_frames
# from pose.landmark_extractor import extract_landmarks

logger = logging.getLogger(__name__)


def run_pose_pipeline(landmark_payload: dict, session_id: str) -> dict:
    """
    Orchestrates the pose analysis pipeline.

    Args:
        landmark_payload: Parsed JSON dict from the 'pose_landmarks' multipart field.
                          Contains 'frames' list with per-frame landmark arrays.
                          Sent by the React Native frontend (BlazePose/TF.js).
        session_id:       UUID string for this session.

    Returns:
        Pose JSON dict (same structure as before — downstream unchanged).

    Pipeline stages:
        landmark_parser     → parse frontend JSON into (33,4) arrays per frame
        normalizer          → hip-anchor translation + torso-length scaling
        metrics             → 10 posture metric functions
        aggregator          → frame → 5s window → session aggregation
        derived_attributes  → 6 behavioral composite scores
        json_builder        → final pose JSON assembly
    """
    # Stage 1 — Parse (replaces frame_extractor + landmark_extractor)
    landmarks = parse_landmark_payload(landmark_payload)

    # Stage 2 — Normalize (UNCHANGED)
    normalized = normalize_landmarks(landmarks)

    # Stage 3 — Metrics (UNCHANGED)
    frame_metrics = compute_all_metrics(normalized)

    # Stage 4 — Aggregate (UNCHANGED)
    window_scores = aggregate_windows(frame_metrics)
    session_scores = aggregate_session(window_scores)

    # Stage 5 — Derived attributes (UNCHANGED)
    derived = compute_derived_attributes(session_scores)

    # Stage 6 — Build output JSON (UNCHANGED)
    return build_pose_json(session_scores, derived, session_id)
```

---

### 4.4 Update: `pose/routes.py`

The route no longer accepts a video file for pose. It accepts the `pose_landmarks` JSON field from the multipart request.

```python
# pose/routes.py

from flask import Blueprint, request, jsonify
from pose.pipeline import run_pose_pipeline
import uuid, os, logging, json

pose_bp = Blueprint("pose", __name__, url_prefix="/pose")
logger  = logging.getLogger(__name__)


@pose_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    Accepts landmark JSON from the React Native frontend (BlazePose/TF.js).

    Multipart field: 'pose_landmarks' — JSON file containing frame-by-frame
    landmark arrays extracted on-device.

    This route no longer accepts video files. The video processing
    (frame extraction + MediaPipe inference) has moved to the mobile device.
    """
    if "pose_landmarks" not in request.files:
        return jsonify({"error": "Missing field: pose_landmarks"}), 400

    session_id = request.form.get("session_id", str(uuid.uuid4()))
    logger.info(f"[{session_id}] Pose pipeline starting — parsing landmark JSON")

    landmark_file = request.files["pose_landmarks"]

    try:
        landmark_payload = json.loads(landmark_file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"[{session_id}] Failed to parse landmark JSON: {e}")
        return jsonify({"error": "Invalid landmark JSON payload"}), 400

    try:
        result = run_pose_pipeline(landmark_payload, session_id)
        logger.info(f"[{session_id}] Pose pipeline complete")
        return jsonify(result), 200
    except ValueError as e:
        logger.error(f"[{session_id}] Landmark payload invalid: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"[{session_id}] Pose pipeline failed: {e}")
        return jsonify({"error": "Pose processing failed"}), 500
    # No temp file cleanup needed — no file written to disk
```

---

### 4.5 Update: Orchestrator Route `/analyze/full`

The orchestrator that runs pose + audio in parallel must be updated to extract `pose_landmarks` from the multipart request instead of saving a video file.

```python
# orchestrator/routes.py (or wherever /analyze/full is defined)

# REMOVE — video file handling
# video_file = request.files['video']
# tmp_path = f"/tmp/{session_id}.mp4"
# video_file.save(tmp_path)

# ADD — landmark JSON extraction
import json

landmark_file = request.files.get("pose_landmarks")
audio_file    = request.files.get("audio")

if not landmark_file:
    return jsonify({"error": "Missing field: pose_landmarks"}), 400
if not audio_file:
    return jsonify({"error": "Missing field: audio"}), 400

try:
    landmark_payload = json.loads(landmark_file.read().decode("utf-8"))
except (json.JSONDecodeError, UnicodeDecodeError):
    return jsonify({"error": "Invalid landmark JSON"}), 400

# Save audio to temp file (audio pipeline still needs a file path)
audio_ext  = "m4a"
audio_path = f"/tmp/{session_id}.{audio_ext}"
audio_file.save(audio_path)

# Run pipelines in parallel — pass landmark_payload dict to pose, audio_path to audio
def run_pose():
    return run_pose_pipeline(landmark_payload, session_id)

def run_audio():
    return run_audio_pipeline(audio_path, session_id)

# ThreadPoolExecutor usage remains unchanged
```

---

### 4.6 Remove MediaPipe from Dependencies

```bash
# requirements.txt — remove these lines:
mediapipe==0.10.x
opencv-python==4.x.x  # remove ONLY if not used elsewhere
                       # check audio preprocessor — PyDub may still need it
```

If `opencv-python` is used only in `frame_extractor.py` (which is now deleted), remove it. If it is imported anywhere else in the codebase, keep it.

```bash
# Verify before removing:
grep -r "import cv2" backend/
grep -r "from cv2" backend/
```

---

### 4.7 config.py — Remove Frame Extraction Constants

These constants were used only by the deleted files. Remove them to keep `config.py` clean.

```python
# REMOVE from config.py:
TARGET_FPS = 30               # was used by frame_extractor.py
FRAME_RESIZE_WIDTH = 640      # was added in action_plan2.md for frame_extractor
FRAME_RESIZE_HEIGHT = 360     # was added in action_plan2.md for frame_extractor
```

`MIN_VISIBILITY_THRESHOLD` stays — it is now used by `landmark_parser.py`.

---

### 4.8 What Backend Developers Must NOT Change

These files are completely untouched by this migration. Do not modify them.

| File | Reason |
|---|---|
| `pose/normalizer.py` | Receives identical (33,4) landmark arrays — contract unchanged |
| `pose/metrics.py` | Receives identical normalized landmark dicts — unchanged |
| `pose/aggregator.py` | Receives identical frame metric dicts — unchanged |
| `pose/derived_attributes.py` | Receives identical session scores — unchanged |
| `pose/json_builder.py` | Unchanged |
| All `audio/` files | Audio pipeline is completely unaffected |
| All `evaluation/` files | Evaluation engine is completely unaffected |
| `config.py` (except removals above) | All metric thresholds, weights unchanged |

---

## 5. Integration Checklist

Use this before marking the migration complete. Both developers sign off on their section.

### Frontend Developer Checklist

- [ ] `react-native-vision-camera` installed and plugin added to `app.json`
- [ ] `@tensorflow/tfjs-react-native`, `@tensorflow/tfjs-backend-webgl`, `@tensorflow-models/pose-detection` installed
- [ ] `react-native-compressor` uninstalled
- [ ] `expo-av` installed for audio recording
- [ ] `src/utils/blazePoseSetup.ts` created — model initializes once at app launch
- [ ] `src/types/pose.ts` created — `LandmarkPoint`, `LandmarkFrame`, `PoseLandmarkPayload` types defined
- [ ] `src/hooks/useBlazePoseRecording.ts` created — frame processor disposes tensors every frame
- [ ] `src/hooks/useSessionUpload.ts` updated — sends `pose_landmarks` JSON + `audio` file, no video
- [ ] `RecordingScreen.tsx` uses `Camera` from VisionCamera, not `CameraView` from expo-camera
- [ ] `ProcessingScreen.tsx` has no 'compressing' sub-state
- [ ] `src/types/navigation.ts` updated — `Processing` params use `landmarkPayload` + `audioUri`
- [ ] `src/utils/compressVideo.ts` deleted
- [ ] BlazePose model preloaded on `DashboardScreen` mount
- [ ] Dev Client rebuilt after `app.json` plugin change
- [ ] Tested on physical Android device — confirmed landmark frames captured and uploaded
- [ ] Confirmed tensor dispose called every frame — no memory crash after 60s recording

### Backend Developer Checklist

- [ ] `pose/frame_extractor.py` deleted
- [ ] `pose/landmark_extractor.py` deleted
- [ ] `pose/landmark_parser.py` created — `parse_landmark_payload()` implemented
- [ ] `pose/pipeline.py` updated — calls `parse_landmark_payload()`, not `extract_frames/landmarks`
- [ ] `pose/routes.py` updated — reads `pose_landmarks` file field, not `video` file
- [ ] Orchestrator `/analyze/full` updated — reads `pose_landmarks` + `audio` fields
- [ ] `mediapipe` removed from `requirements.txt`
- [ ] `opencv-python` removal verified (check all remaining imports first)
- [ ] `TARGET_FPS`, `FRAME_RESIZE_WIDTH`, `FRAME_RESIZE_HEIGHT` removed from `config.py`
- [ ] `MIN_VISIBILITY_THRESHOLD` kept in `config.py` — used by `landmark_parser.py`
- [ ] Deployed to Render — confirmed no import errors on startup
- [ ] Tested with landmark JSON payload from frontend — full pipeline completes successfully
- [ ] Confirmed `normalizer.py`, `metrics.py`, `aggregator.py` output unchanged

---

## 6. Error Handling Contract

### Frontend — What to Do When BlazePose Inference Fails for a Frame

Never crash or stop recording. Log the frame miss and continue.

```typescript
// Inside frame processor:
try {
  // ... inference
} catch (err) {
  console.warn('[BlazePose] Frame dropped:', err);
  // Do not push to landmarkBufferRef — sparse frames are fine
  // aggregator.py handles variable frame density via timestamp windowing
}
```

If the landmark buffer is empty when the user stops recording (model never initialized or all frames failed), do not upload — show the user an error and prompt them to re-record.

```typescript
if (landmarkPayload.total_frames === 0) {
  Alert.alert(
    'Recording Issue',
    'No pose data was captured. Please try recording again.',
    [{ text: 'OK' }]
  );
  return;
}
```

### Backend — What to Do When Landmark JSON is Invalid

`landmark_parser.py` handles invalid individual frames gracefully by marking them `valid=False`. The pipeline continues with remaining valid frames.

If the entire payload is malformed (missing `frames` field, not valid JSON), `pose/routes.py` returns 400 immediately before the pipeline runs.

If valid frame count falls below a meaningful threshold, `json_builder.py` should log a warning but still return results — the evaluation engine handles low-confidence sessions.

---

## 7. Testing Instructions

### Frontend — Manual Test on Physical Device

1. Build and install Dev Client on a physical Android device (not simulator — TF.js WebGL requires GPU)
2. Navigate to Recording Screen
3. Verify "Model Ready" state is reached within 8 seconds of Dashboard mount
4. Start a 30-second recording — observe no UI jank or crash
5. Stop recording — verify `landmarkPayload.total_frames > 0` in console log
6. Verify upload completes and results screen is reached

### Backend — Unit Test for `landmark_parser.py`

```python
# tests/test_pose_landmark_parser.py

import numpy as np
from pose.landmark_parser import parse_landmark_payload

def make_test_landmark():
    return {"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.95}

def make_test_frame(timestamp: float):
    return {
        "timestamp": timestamp,
        "landmarks": [make_test_landmark() for _ in range(33)],
    }

def make_test_payload(num_frames: int = 10):
    return {
        "session_id": "test-session-id",
        "user_id": "test-user-id",
        "fps_achieved": 22.0,
        "total_frames": num_frames,
        "duration_seconds": float(num_frames) / 22.0,
        "frames": [make_test_frame(i / 22.0) for i in range(num_frames)],
    }

def test_parse_returns_correct_length():
    payload = make_test_payload(50)
    result = parse_landmark_payload(payload)
    assert len(result) == 50

def test_each_frame_has_correct_shape():
    payload = make_test_payload(5)
    result = parse_landmark_payload(payload)
    for frame in result:
        assert frame["landmarks"].shape == (33, 4)
        assert isinstance(frame["timestamp"], float)
        assert isinstance(frame["valid"], bool)

def test_valid_frame_marked_valid():
    payload = make_test_payload(1)
    result = parse_landmark_payload(payload)
    assert result[0]["valid"] is True

def test_low_visibility_frame_marked_invalid():
    payload = make_test_payload(1)
    # Set all landmark visibility to 0.0
    for lm in payload["frames"][0]["landmarks"]:
        lm["visibility"] = 0.0
    result = parse_landmark_payload(payload)
    assert result[0]["valid"] is False

def test_wrong_landmark_count_marks_invalid():
    payload = make_test_payload(1)
    payload["frames"][0]["landmarks"] = payload["frames"][0]["landmarks"][:20]
    result = parse_landmark_payload(payload)
    assert result[0]["valid"] is False

def test_missing_frames_field_raises():
    import pytest
    with pytest.raises(ValueError, match="missing required field"):
        parse_landmark_payload({"session_id": "x"})

def test_timestamps_are_monotonic():
    payload = make_test_payload(10)
    result = parse_landmark_payload(payload)
    timestamps = [f["timestamp"] for f in result]
    assert timestamps == sorted(timestamps)
```

---

*Document version 1.0 | Architecture migration: Backend MediaPipe → On-Device BlazePose (TF.js RN)*
*Frontend: React Native + Expo Dev Client + VisionCamera + TF.js*
*Backend: Python/Flask — normalizer.py onward unchanged*
