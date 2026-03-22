# Public Speaking Coach App — Feature Integration Specification
## Tasks: T1 · T2 · T3

**Version:** 1.1  
**Date:** 2026-03-16  
**Prepared by:** Product / Architecture  
**For:** Frontend Team · Backend Team · LLM-assisted editors (Gemini CLI)  

> **How to use this document:** Each section is self-contained. Frontend and backend jobs are explicitly labelled. Every code block is copy-paste ready. Read the Architecture Constraints section before writing any code.

> **v1.1 changelog:** T1 updated — added `QuoteCard` locked/unlocked gate mechanic (JOB FE-T1-5). The existing `QuoteCard` component on `DashboardScreen` now acts as the session completion reward: blurred + locked until the user completes one session today, unlocked and full-opacity once they do. No backend changes required for this addition.

---

## Table of Contents

1. [Architecture Constraints — Read First](#1-architecture-constraints--read-first)
2. [T1 — Practice Streak & Skill Fingerprint Module](#2-t1--practice-streak--skill-fingerprint-module)
3. [T2 — Session Activity Card (Strava-Style Viral Share)](#3-t2--session-activity-card-strava-style-viral-share)
4. [T3 — Offline Record & Queue Mode](#4-t3--offline-record--queue-mode)
5. [New File Manifest](#5-new-file-manifest)
6. [Modified File Manifest](#6-modified-file-manifest)
7. [Supabase Schema Additions](#7-supabase-schema-additions)
8. [Integration Order & Dependencies](#8-integration-order--dependencies)
9. [Testing Checklist](#9-testing-checklist)

---

## 1. Architecture Constraints — Read First

These constraints are non-negotiable. Every implementation decision in this document respects them. If you see a conflict, raise it before writing code.

### 1.1 Existing Laws (from `frontendImplementation_plan.md`)

| Law | What it means for this feature set |
|-----|-------------------------------------|
| **Cache-first, network-never for history** | T1 streak data reads from `AsyncStorage` only — zero Supabase reads on dashboard mount |
| **Write-before-display** | T3 queued session must be fully written to `offlineQueue` before navigation leaves `RecordingScreen` |
| **No magic numbers** | All thresholds (streak milestones, queue cap, card dimensions) live in `src/theme/constants.ts` — not inline |
| **Stateless modules** | `offlineQueue.ts`, `shareCard.ts`, `streakStore.ts` must hold no module-level mutable state |
| **EvaluationResult is the canonical type** | T1 streak colors derive from `overall_scores.overall`; T2 card data comes from `EvaluationResult` — never re-shape the type |

### 1.2 New Dependencies Required

Install these before starting. Run in order.

```bash
# T2 — Share card image capture
npm install react-native-view-shot

# T3 — Connectivity detection
npx expo install expo-network

# T3 + T1 — Push notifications (streak milestone + queue result ready)
npx expo install expo-notifications
npx expo install expo-task-manager

# T2 — Share sheet (already in Expo, confirm it's imported)
# expo-sharing is part of expo SDK — no install needed
```

After installing, rebuild the Dev Client:
```bash
npx expo prebuild
npx expo run:ios   # or run:android
```

### 1.3 New Constants File

Create `src/theme/constants.ts` immediately. All feature numbers go here.

```typescript
// src/theme/constants.ts

export const STREAK = {
  MILESTONE_DAYS: [3, 7, 14, 30],       // Days that trigger motivational tip fetch
  SKILL_KEYS: ['confidence', 'clarity', 'engagement', 'nervousness'] as const,
  GRID_SIZE: 8,                           // 4x2 grid squares on dashboard
} as const;

export const OFFLINE_QUEUE = {
  MAX_SESSIONS: 3,                        // Hard cap on queued sessions
  RETRY_MAX: 3,                           // Max upload retry attempts per session
  RETRY_DELAY_MS: 5_000,                 // Delay between retries
  BACKGROUND_TASK_NAME: 'QUEUE_DRAIN',   // expo-task-manager identifier
} as const;

export const SHARE_CARD = {
  WIDTH: 1080,
  HEIGHT: 1080,
  BACKGROUND: '#0D0D0D',
  ACCENT: '#1152D4',
  GREEN: '#39D353',
} as const;
```

---

## 2. T1 — Practice Streak & Skill Fingerprint Module

### 2.1 What We Are Building

**Not** a simple flame counter. We are building a **Skill Fingerprint** — the streak tracks consistency per coaching dimension (confidence, clarity, engagement, nervousness) independently. The dashboard shows a 4×2 activity grid (GitHub-style, already designed) plus a `StreakMilestoneTip` card that appears the moment a 3-day streak is hit in any skill dimension.

The visual difference from the baseline task: instead of one green flame saying "3-day streak", the user sees _which skill_ they've been consistently improving — "3-day confidence streak". This is motivationally specific and signals the app is actually watching their growth.

**Additionally — QuoteCard Daily Gate (v1.1 addition):**  
The existing `<QuoteCard />` component already lives on `DashboardScreen` and rotates daily quotes at midnight. We are repurposing it as a **session completion reward**. The mechanic:

- **Before today's session:** `QuoteCard` renders with a blur overlay, the quote text is unreadable, and a centered lock state shows: a play icon + the label _"Complete today's session to unlock"_. Tapping anywhere on the locked card navigates the user to `RecordingScreen`.
- **After today's session is saved:** The blur lifts, the quote is fully visible, and the card behaves exactly as it does today.

This creates a lightweight daily ritual — the quote becomes something the user *earns*, not just reads. It also turns the `QuoteCard` into a passive re-engagement CTA on days the user hasn't practised yet.

**Unlock condition:** A session counts as "today's" if a `SessionListEntry` exists in the local cache whose `processedAt` date matches today's calendar date in the device's local timezone. This is a pure cache read — no network call, no new state.

### 2.2 Data Model

No new Supabase tables are needed for streak computation. Streak is computed entirely from the local `SessionListEntry[]` cache.

One new Supabase table is needed for motivational tips (read-only, fetched only on milestone hit):

```sql
-- See Section 7 for full Supabase schema
CREATE TABLE motivational_tips (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  streak_milestone int NOT NULL,      -- 3, 7, 14, 30
  skill_focus text NOT NULL,          -- 'confidence' | 'clarity' | 'engagement' | 'overall'
  tip_text text NOT NULL,
  created_at timestamptz DEFAULT now()
);
```

### 2.3 Frontend Jobs

---

#### JOB FE-T1-1: Create `src/store/streakStore.ts`

```typescript
// src/store/streakStore.ts

import { create } from 'zustand';
import { SessionListEntry } from '../types/cache';
import { STREAK } from '../theme/constants';
import { getRecentSessions } from '../cache/sessionCache';
import apiClient from '../api/client';

export interface SkillStreak {
  skill: typeof STREAK.SKILL_KEYS[number] | 'overall';
  currentStreak: number;    // consecutive days with a session
  longestStreak: number;
  lastMilestoneShown: number; // last milestone we fetched a tip for
}

export interface StreakState {
  sessions: SessionListEntry[];           // last 8, for grid display
  skillStreaks: SkillStreak[];
  milestoneTip: string | null;            // non-null when a new milestone is hit
  milestoneTipSkill: string | null;
  hasCompletedTodaySession: boolean;      // drives QuoteCard locked/unlocked state
  isLoading: boolean;
  refresh: () => Promise<void>;
  dismissMilestoneTip: () => void;
}

export const useStreakStore = create<StreakState>((set, get) => ({
  sessions: [],
  skillStreaks: [],
  milestoneTip: null,
  milestoneTipSkill: null,
  hasCompletedTodaySession: false,
  isLoading: false,

  refresh: async () => {
    set({ isLoading: true });
    const sessions = await getRecentSessions(STREAK.GRID_SIZE);
    const skillStreaks = computeSkillStreaks(sessions);
    const hasCompletedTodaySession = checkTodaySession(sessions);
    set({ sessions, skillStreaks, hasCompletedTodaySession, isLoading: false });

    // Check for new milestones — fetch tip from Supabase only on milestone hit
    const { milestoneTip } = get();
    if (!milestoneTip) {
      await checkAndFetchMilestoneTip(skillStreaks, set);
    }
  },

  dismissMilestoneTip: () => set({ milestoneTip: null, milestoneTipSkill: null }),
}));

// ── Streak computation (pure, no side effects) ─────────────────────────────────

function checkTodaySession(sessions: SessionListEntry[]): boolean {
  // Uses device local timezone — matches the user's intuitive definition of "today"
  const todayKey = new Date().toLocaleDateString('sv'); // 'YYYY-MM-DD' in local TZ
  return sessions.some((s) => {
    const sessionKey = new Date(s.processedAt).toLocaleDateString('sv');
    return sessionKey === todayKey;
  });
}

function computeSkillStreaks(sessions: SessionListEntry[]): SkillStreak[] {
  // Sessions are sorted newest-first from getRecentSessions
  // A "streak day" = any calendar day with at least one session
  const keys: Array<typeof STREAK.SKILL_KEYS[number] | 'overall'> = [
    ...STREAK.SKILL_KEYS, 'overall',
  ];

  return keys.map((skill) => {
    let current = 0;
    let longest = 0;
    let prevDate: string | null = null;

    for (const session of sessions) {
      const dateKey = session.processedAt.slice(0, 10); // 'YYYY-MM-DD'
      if (dateKey === prevDate) continue; // multiple sessions same day = 1 streak day

      const score =
        skill === 'overall'
          ? session.overallScore
          : (session as any)[`${skill}Score`] ?? session.overallScore;

      if (score >= 0.40) { // any "medium" or above session keeps streak alive
        current++;
        longest = Math.max(longest, current);
      } else {
        current = 0;
      }
      prevDate = dateKey;
    }

    return {
      skill,
      currentStreak: current,
      longestStreak: longest,
      lastMilestoneShown: 0,
    };
  });
}

async function checkAndFetchMilestoneTip(
  skillStreaks: SkillStreak[],
  set: (partial: Partial<StreakState>) => void,
) {
  for (const sk of skillStreaks) {
    const nextMilestone = STREAK.MILESTONE_DAYS.find(
      (m) => m <= sk.currentStreak && m > sk.lastMilestoneShown,
    );
    if (nextMilestone) {
      try {
        const { data } = await apiClient.get(
          `/streak/tip?milestone=${nextMilestone}&skill=${sk.skill}`,
        );
        if (data?.tip_text) {
          set({
            milestoneTip: data.tip_text,
            milestoneTipSkill: sk.skill,
          });
          sk.lastMilestoneShown = nextMilestone;
        }
      } catch {
        // Network failure — no tip shown, user not disrupted
      }
      break; // Show at most one tip per refresh
    }
  }
}
```

---

#### JOB FE-T1-2: Add `SessionListEntry` skill score fields to `src/types/cache.ts`

The existing `SessionListEntry` only stores `overallScore` and `confidenceScore`. We need all four skill scores for per-skill streak computation.

```typescript
// src/types/cache.ts — MODIFY EXISTING SessionListEntry interface

export interface SessionListEntry {
  sessionId:        string;
  processedAt:      string;
  overallScore:     number;    // [0, 1] — existing
  confidenceScore:  number;    // [0, 1] — existing
  // ADD THESE THREE:
  clarityScore:     number;    // [0, 1]
  engagementScore:  number;    // [0, 1]
  nervousnessScore: number;    // [0, 1]
  topicTitle:       string;
  durationLabel:    string;
  isFirstSession:   boolean;
}
```

**Also update `saveSession` in `src/cache/sessionCache.ts`** to populate the new fields:

```typescript
// Inside saveSession() — update the entry construction:
const entry: SessionListEntry = {
  sessionId:        result.session_metadata.session_id,
  processedAt:      result.session_metadata.processed_at,
  overallScore:     result.overall_scores.overall,
  confidenceScore:  result.overall_scores.confidence,
  clarityScore:     result.overall_scores.clarity,       // ADD
  engagementScore:  result.overall_scores.engagement,    // ADD
  nervousnessScore: result.overall_scores.nervousness,   // ADD
  topicTitle,
  durationLabel:    formatElapsedSeconds(elapsedSeconds),
  isFirstSession:   result.session_metadata.is_first_session,
};
```

---

#### JOB FE-T1-3: Create `src/components/dashboard/StreakMilestoneTip.tsx`

This card appears at the top of the dashboard when a new streak milestone is hit. It is dismissable.

```typescript
// src/components/dashboard/StreakMilestoneTip.tsx

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors } from '../../theme/colors';
import { spacing } from '../../theme/spacing';
import { fonts, fontSize } from '../../theme/typography';

interface Props {
  tip: string;
  skill: string;
  onDismiss: () => void;
}

export const StreakMilestoneTip: React.FC<Props> = ({ tip, skill, onDismiss }) => (
  <View style={styles.card}>
    <View style={styles.header}>
      <View style={styles.flameBadge}>
        <Text style={styles.flameEmoji}>🔥</Text>
        <Text style={styles.badgeText}>{skill.charAt(0).toUpperCase() + skill.slice(1)} streak</Text>
      </View>
      <TouchableOpacity onPress={onDismiss} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <MaterialIcons name="close" size={18} color={colors.textSecondary} />
      </TouchableOpacity>
    </View>
    <Text style={styles.tip}>{tip}</Text>
  </View>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceDark,
    borderRadius: 16,
    padding: spacing.base,
    borderWidth: 0.5,
    borderColor: 'rgba(57, 211, 83, 0.3)', // streakHigh with low opacity
    marginBottom: spacing.base,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  flameBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(57, 211, 83, 0.12)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  flameEmoji: { fontSize: 14 },
  badgeText: {
    fontFamily: fonts.medium,
    fontSize: fontSize.xs,
    color: colors.streakHigh,
  },
  tip: {
    fontFamily: fonts.regular,
    fontSize: fontSize.sm,
    color: colors.textSecondary,
    lineHeight: 20,
  },
});
```

---

#### JOB FE-T1-4: Update `src/screens/DashboardScreen.tsx`

Wire up `useStreakStore` and render the milestone tip card. Replace the existing hardcoded streak data read with the store.

```typescript
// DashboardScreen.tsx — key changes only (merge into existing file)

import { useStreakStore } from '../store/streakStore';

// Inside component:
const { sessions, skillStreaks, milestoneTip, milestoneTipSkill, refresh, dismissMilestoneTip } =
  useStreakStore();

// Call refresh on focus (not every render):
useFocusEffect(useCallback(() => { refresh(); }, []));

// In JSX, above the PerformanceGrid:
{milestoneTip && milestoneTipSkill && (
  <StreakMilestoneTip
    tip={milestoneTip}
    skill={milestoneTipSkill}
    onDismiss={dismissMilestoneTip}
  />
)}

// Pass `sessions` prop to StreakSection instead of reading separately:
<StreakSection sessions={sessions} onPress={() => navigation.navigate('SessionHistory')} />
```

---

#### JOB FE-T1-5: Gate `<QuoteCard />` on daily session completion in `src/screens/DashboardScreen.tsx`

This job modifies how the **existing** `<QuoteCard />` component is rendered on the dashboard. The component itself does **not** need to be rewritten — we wrap it with a locking layer. All logic lives in `DashboardScreen.tsx`.

**Visual spec for the locked state:**

```
┌──────────────────────────────────────────────────────┐
│  [blurred quote text — unreadable, opacity ~0.25]    │
│                                                      │
│            ▶  Complete today's session               │
│               to unlock                              │
│                                                      │
└──────────────────────────────────────────────────────┘
```

- The `<QuoteCard />` renders underneath at reduced opacity (`0.18`) — visible enough to hint that content exists, illegible enough that it can't be read.
- A full-coverage `TouchableOpacity` overlay sits on top with the play icon and message.
- The entire locked card is tappable — tapping navigates to `RecordingScreen` with today's topic.
- On unlock (session completed today), the overlay disappears with a fade animation. No page reload required — `useFocusEffect` calling `refresh()` handles the state update when the user returns from the results screen.

**Implementation — add to `DashboardScreen.tsx`:**

```typescript
// DashboardScreen.tsx — additions for QuoteCard gate (merge into existing file)

import React, { useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Animated
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { colors } from '../theme/colors';
import { fonts, fontSize } from '../theme/typography';
import { spacing } from '../theme/spacing';
import { useStreakStore } from '../store/streakStore';

// Inside component — read unlock state from store (already wired via FE-T1-4):
const { hasCompletedTodaySession } = useStreakStore();

// Fade animation — runs once when hasCompletedTodaySession flips true:
const overlayOpacity = useRef(new Animated.Value(hasCompletedTodaySession ? 0 : 1)).current;

useEffect(() => {
  if (hasCompletedTodaySession) {
    Animated.timing(overlayOpacity, {
      toValue: 0,
      duration: 600,
      useNativeDriver: true,
    }).start();
  }
}, [hasCompletedTodaySession]);

// In JSX — replace bare <QuoteCard /> with this wrapper:
<View style={styles.quoteCardWrapper}>
  {/* The existing QuoteCard — always rendered, dimmed when locked */}
  <View style={[
    styles.quoteCardInner,
    !hasCompletedTodaySession && styles.quoteCardDimmed,
  ]}>
    <QuoteCard />
  </View>

  {/* Lock overlay — fades out after session completion */}
  <Animated.View
    style={[styles.lockOverlay, { opacity: overlayOpacity }]}
    pointerEvents={hasCompletedTodaySession ? 'none' : 'auto'}
  >
    <TouchableOpacity
      style={styles.lockContent}
      activeOpacity={0.8}
      onPress={() => navigation.navigate('Recording', {
        topicTitle:         TODAY_TOPIC.title,
        minDurationSeconds: TODAY_TOPIC.minDurationSeconds,
      })}
      accessibilityRole="button"
      accessibilityLabel="Complete today's session to unlock daily quote. Tap to start recording."
    >
      <View style={styles.playIconCircle}>
        <MaterialIcons name="play-arrow" size={28} color={colors.textPrimary} />
      </View>
      <Text style={styles.lockTitle}>Complete today's session</Text>
      <Text style={styles.lockSubtitle}>to unlock</Text>
    </TouchableOpacity>
  </Animated.View>
</View>

// ── Styles to add to the existing StyleSheet.create({}) block ──────────────────

quoteCardWrapper: {
  position: 'relative',
  borderRadius: 16,
  overflow: 'hidden',       // clips the overlay to the card's rounded corners
},
quoteCardInner: {
  // no style change when unlocked — QuoteCard renders at full opacity
},
quoteCardDimmed: {
  opacity: 0.18,            // quote text is visible as a hint but not readable
},
lockOverlay: {
  ...StyleSheet.absoluteFillObject,
  backgroundColor: colors.surfaceDark,  // matches card bg — no bleed
  borderRadius: 16,
  justifyContent: 'center',
  alignItems: 'center',
  borderWidth: 0.5,
  borderColor: colors.borderMuted,
},
lockContent: {
  alignItems: 'center',
  gap: spacing.sm,
  paddingHorizontal: spacing.xl,
},
playIconCircle: {
  width: 52,
  height: 52,
  borderRadius: 26,
  backgroundColor: colors.buttonDark,
  borderWidth: 0.5,
  borderColor: colors.borderDark,
  justifyContent: 'center',
  alignItems: 'center',
  marginBottom: spacing.xs,
},
lockTitle: {
  fontFamily: fonts.medium,
  fontSize: fontSize.sm,
  color: colors.textSecondary,
  textAlign: 'center',
},
lockSubtitle: {
  fontFamily: fonts.regular,
  fontSize: fontSize.xs,
  color: colors.textMuted,
  textAlign: 'center',
},
```

**Important notes for the developer:**

1. `overflow: 'hidden'` on `quoteCardWrapper` is mandatory — without it the overlay's `borderRadius` won't clip on Android.
2. `pointerEvents="none"` on the `Animated.View` after unlock means the lock overlay accepts zero touches after fading out — the `QuoteCard` underneath receives taps normally.
3. Do **not** conditionally unmount `<QuoteCard />` based on the lock state. It must always be mounted so its daily-rotation logic (your existing midnight swap) keeps running.
4. The `useEffect` on `hasCompletedTodaySession` only animates in one direction — locked → unlocked. On app relaunch when already unlocked, `overlayOpacity` initialises to `0` directly (no animation flash).

---

---

### 2.4 Backend Jobs

---

#### JOB BE-T1-1: Add `/streak/tip` endpoint

**Route:** `GET /streak/tip?milestone=<int>&skill=<string>`  
**Auth:** Bearer token required  
**Response:**

```json
{
  "tip_text": "You've been speaking with consistent confidence for 3 days...",
  "milestone": 3,
  "skill": "confidence"
}
```

**Implementation notes:**
- Query `motivational_tips` table in Supabase where `streak_milestone = milestone AND skill_focus = skill`
- Return one row at random (`ORDER BY RANDOM() LIMIT 1`)
- If no matching tip exists, return `{ "tip_text": null }` — frontend handles null silently
- Response is cached with a 24-hour TTL (add `Cache-Control: max-age=86400` header) — this endpoint will be hammered on 3-day milestone days

**Flask blueprint:** Add to a new `streak/routes.py` inside its own blueprint, registered at `/streak`.

```python
# streak/routes.py
from flask import Blueprint, request, jsonify
from supabase import create_client
import os, random

streak_bp = Blueprint('streak', __name__, url_prefix='/streak')

@streak_bp.route('/tip', methods=['GET'])
def get_streak_tip():
    milestone = request.args.get('milestone', type=int)
    skill     = request.args.get('skill', type=str)

    if milestone not in [3, 7, 14, 30] or not skill:
        return jsonify({'error': 'invalid params'}), 400

    supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
    result = (
        supabase.table('motivational_tips')
        .select('tip_text')
        .eq('streak_milestone', milestone)
        .eq('skill_focus', skill)
        .execute()
    )

    rows = result.data
    if not rows:
        return jsonify({'tip_text': None}), 200

    tip = random.choice(rows)['tip_text']
    response = jsonify({'tip_text': tip, 'milestone': milestone, 'skill': skill})
    response.headers['Cache-Control'] = 'max-age=86400'
    return response
```

**Register in `app.py`:**
```python
from streak.routes import streak_bp
app.register_blueprint(streak_bp)
```

---

## 3. T2 — Session Activity Card (Strava-Style Viral Share)

### 3.1 What We Are Building

**Not a PDF.** We are building a **1080×1080 shareable image card** — the visual equivalent of a Strava activity card — designed to be posted as an Instagram story, WhatsApp status, or sent to a mentor. The card renders off-screen using `react-native-view-shot`, captures it as a PNG, and shares it via the native share sheet.

**Why this works (the Strava lesson):** Strava went viral because the post-run card was beautiful enough to post as identity content. Our card shows the user looking competent and analytical. Students will share it to placement cells. Job seekers will share it to interviewers. Every share is a zero-CAC app install for us.

**The card layout:**

```
┌────────────────────────────────────────────────┐
│  🎙 SpeakingCoach                    [logo]    │
├────────────────────────────────────────────────┤
│                                                │
│         OVERALL SCORE                         │
│              82%                              │  ← big, bold, centered
│                                                │
│  ─────────────────────────────────────────    │
│                                                │
│  Confidence  Clarity  Engagement  Nervousness │
│     78%       74%       69%          32%      │  ← 4 metric pills
│                                                │
│  ─────────────────────────────────────────    │
│                                                │
│  "Keep up the steady work; each focused       │
│   effort brings you closer to confident,      │
│   engaging speaking."                         │  ← LLM motivational closing
│                                                │
│  ─────────────────────────────────────────    │
│                                                │
│  Leadership Under Pressure  •  14m 23s        │  ← topic + duration
│  March 16, 2026                               │
└────────────────────────────────────────────────┘
```

### 3.2 No Backend Work Required

T2 is entirely frontend. All data is already in `sessionStore.latestResult` (live session) or `EvaluationResult` (cached session). Zero new API calls.

### 3.3 Frontend Jobs

---

#### JOB FE-T2-1: Create `src/components/ui/SessionActivityCard.tsx`

This component renders the shareable card. It is only mounted when the user taps Share — it renders off-screen and is captured immediately.

```typescript
// src/components/ui/SessionActivityCard.tsx

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { EvaluationResult } from '../../types/api';
import { SHARE_CARD } from '../../theme/constants';
import { toPercent } from '../../utils/toPercent';

interface Props {
  result: EvaluationResult;
  topicTitle: string;
  durationLabel: string;
  sessionDate: string;  // formatted: "March 16, 2026"
}

export const SessionActivityCard = React.forwardRef<View, Props>(
  ({ result, topicTitle, durationLabel, sessionDate }, ref) => {
    const { overall, confidence, clarity, engagement, nervousness } =
      result.overall_scores;
    const closing = result.llm_feedback.motivational_closing;

    const metrics = [
      { label: 'Confidence',  value: confidence },
      { label: 'Clarity',     value: clarity },
      { label: 'Engagement',  value: engagement },
      { label: 'Nervousness', value: nervousness },
    ];

    return (
      <View ref={ref} style={styles.card}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.appName}>🎙 SpeakingCoach</Text>
          <Text style={styles.headerRight}>AI Coach</Text>
        </View>

        <View style={styles.divider} />

        {/* Overall score */}
        <View style={styles.scoreBlock}>
          <Text style={styles.scoreLabel}>OVERALL SCORE</Text>
          <Text style={styles.scoreValue}>{toPercent(overall)}</Text>
        </View>

        <View style={styles.divider} />

        {/* Metric pills */}
        <View style={styles.metricsRow}>
          {metrics.map((m) => (
            <View key={m.label} style={styles.metricPill}>
              <Text style={styles.metricValue}>{toPercent(m.value)}</Text>
              <Text style={styles.metricLabel}>{m.label}</Text>
            </View>
          ))}
        </View>

        <View style={styles.divider} />

        {/* LLM quote */}
        <Text style={styles.quote} numberOfLines={3}>
          "{closing}"
        </Text>

        <View style={styles.divider} />

        {/* Session meta */}
        <View style={styles.footer}>
          <Text style={styles.footerTopic}>{topicTitle}</Text>
          <Text style={styles.footerMeta}>{durationLabel}  ·  {sessionDate}</Text>
        </View>
      </View>
    );
  },
);

SessionActivityCard.displayName = 'SessionActivityCard';

const styles = StyleSheet.create({
  card: {
    width: SHARE_CARD.WIDTH,
    height: SHARE_CARD.HEIGHT,
    backgroundColor: SHARE_CARD.BACKGROUND,
    padding: 80,
    justifyContent: 'space-evenly',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  appName: {
    fontFamily: 'Inter_700Bold',
    fontSize: 42,
    color: '#FFFFFF',
    letterSpacing: -1,
  },
  headerRight: {
    fontFamily: 'Inter_400Regular',
    fontSize: 32,
    color: '#555555',
  },
  divider: {
    height: 1,
    backgroundColor: '#222222',
  },
  scoreBlock: {
    alignItems: 'center',
    paddingVertical: 20,
  },
  scoreLabel: {
    fontFamily: 'Inter_500Medium',
    fontSize: 28,
    color: '#666666',
    letterSpacing: 4,
    marginBottom: 16,
  },
  scoreValue: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: 200,
    color: '#FFFFFF',
    lineHeight: 200,
    letterSpacing: -8,
  },
  metricsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 20,
  },
  metricPill: {
    alignItems: 'center',
    backgroundColor: '#161616',
    borderRadius: 20,
    paddingHorizontal: 30,
    paddingVertical: 20,
    borderWidth: 1,
    borderColor: '#2A2A2A',
    minWidth: 200,
  },
  metricValue: {
    fontFamily: 'Inter_700Bold',
    fontSize: 52,
    color: '#FFFFFF',
    marginBottom: 8,
  },
  metricLabel: {
    fontFamily: 'Inter_400Regular',
    fontSize: 28,
    color: '#888888',
  },
  quote: {
    fontFamily: 'Inter_400Regular',
    fontSize: 38,
    color: '#AAAAAA',
    lineHeight: 56,
    fontStyle: 'italic',
    paddingVertical: 10,
  },
  footer: {
    gap: 12,
  },
  footerTopic: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 40,
    color: '#FFFFFF',
    letterSpacing: -0.5,
  },
  footerMeta: {
    fontFamily: 'Inter_400Regular',
    fontSize: 30,
    color: '#555555',
  },
});
```

---

#### JOB FE-T2-2: Create `src/utils/shareCard.ts`

Capture the card view as a PNG and trigger the native share sheet.

```typescript
// src/utils/shareCard.ts

import { RefObject } from 'react';
import { View } from 'react-native';
import ViewShot from 'react-native-view-shot';
import * as Sharing from 'expo-sharing';
import * as FileSystem from 'expo-file-system';

export async function captureAndShareCard(
  cardRef: RefObject<ViewShot>,
  topicTitle: string,
): Promise<void> {
  if (!cardRef.current) throw new Error('Card ref not ready');

  // Capture the off-screen card as PNG
  const uri = await cardRef.current.capture();

  // Copy to a shareable path with a clean filename
  const filename = `speaking-session-${Date.now()}.png`;
  const destUri = `${FileSystem.cacheDirectory}${filename}`;
  await FileSystem.copyAsync({ from: uri, to: destUri });

  // Check if sharing is available (always true on physical devices)
  const available = await Sharing.isAvailableAsync();
  if (!available) throw new Error('Sharing not available on this device');

  await Sharing.shareAsync(destUri, {
    mimeType: 'image/png',
    dialogTitle: `My ${topicTitle} session — SpeakingCoach`,
    UTI: 'public.png',
  });

  // Cleanup cache after share sheet closes
  setTimeout(() => {
    FileSystem.deleteAsync(destUri, { idempotent: true }).catch(() => {});
  }, 10_000);
}
```

---

#### JOB FE-T2-3: Add Share Button and off-screen card to `src/screens/ResultsScreen.tsx`

The card renders off-screen at all times the ResultsScreen is mounted. The `ViewShot` ref is passed to the card. The share button calls `captureAndShareCard`.

```typescript
// ResultsScreen.tsx — key additions only (merge into existing)

import React, { useRef, useState } from 'react';
import ViewShot from 'react-native-view-shot';
import { SessionActivityCard } from '../components/ui/SessionActivityCard';
import { captureAndShareCard } from '../utils/shareCard';
import dayjs from 'dayjs';

// Inside component:
const cardRef = useRef<ViewShot>(null);
const [isSharing, setIsSharing] = useState(false);
const result = useSessionStore((s) => s.latestResult)!;
const topicTitle = useSessionStore((s) => s.topicTitle);
const elapsedSeconds = useSessionStore((s) => s.elapsedSeconds);
const sessionDate = dayjs(result.session_metadata.processed_at).format('MMMM D, YYYY');
const durationLabel = formatElapsedSeconds(elapsedSeconds);

const handleShare = async () => {
  setIsSharing(true);
  try {
    await captureAndShareCard(cardRef, topicTitle);
  } catch (err) {
    console.error('[Share]', err);
    // Silent fail — user sees share sheet close, no crash
  } finally {
    setIsSharing(false);
  }
};

// Off-screen card (position: absolute, outside viewport but still rendered):
// Add this INSIDE the return, outside the ScrollView:
return (
  <SafeAreaView>
    {/* Off-screen card for capture — invisible to user */}
    <View style={{ position: 'absolute', top: -2000, left: 0, pointerEvents: 'none' }}>
      <ViewShot ref={cardRef} options={{ format: 'png', quality: 1.0 }}>
        <SessionActivityCard
          result={result}
          topicTitle={topicTitle}
          durationLabel={durationLabel}
          sessionDate={sessionDate}
        />
      </ViewShot>
    </View>

    {/* Existing header — update the share button: */}
    {/* Replace the existing share button's onPress with handleShare */}
    {/* Add loading indicator: isSharing ? <ActivityIndicator /> : <ShareIcon /> */}

    {/* ... rest of existing ResultsScreen JSX ... */}
  </SafeAreaView>
);
```

---

#### JOB FE-T2-4: Mirror share button on `src/screens/SessionDetailScreen.tsx`

The Session Detail screen shows cached past sessions. Same card, same share flow. The only difference is `result` comes from the local cache instead of `sessionStore`.

```typescript
// SessionDetailScreen.tsx — additions only

// After loading result from getSessionDetail(sessionId):
const cardRef = useRef<ViewShot>(null);
const sessionDate = dayjs(result.session_metadata.processed_at).format('MMMM D, YYYY');

// Render the same off-screen card and share button pattern from ResultsScreen
// topicTitle comes from SessionListEntry (loaded alongside the detail)
```

---

## 4. T3 — Offline Record & Queue Mode

### 4.1 What We Are Building

Allow users to record a session even without an internet connection. The recorded + compressed video is saved to a local queue. When connectivity is restored, a background task drains the queue automatically — compressing, uploading, and saving results to cache.

When a queued session finishes analysis, a push notification appears: **"Coach's Report Ready — Leadership Under Pressure session analysed."** Tapping it navigates to the result. This transforms what could feel like a loading state into a delight moment.

**Queue cap: 3 sessions.** On the 3rd recording, the user is warned. If a 4th is attempted, a blocking alert fires.

### 4.2 No Backend Work Required

T3 is entirely frontend. The existing `/analyze/full` endpoint is unchanged. We are adding queue management and background execution around the existing `useVideoUpload.ts` logic.

### 4.3 Frontend Jobs

---

#### JOB FE-T3-1: Create `src/cache/offlineQueue.ts`

```typescript
// src/cache/offlineQueue.ts

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system';

const QUEUE_KEY = 'sc_offline_queue_v1';

export interface QueuedSession {
  id:             string;    // uuid — generated at queue time
  videoUri:       string;    // local file path (compressed)
  topicTitle:     string;
  elapsedSeconds: number;
  queuedAt:       string;    // ISO 8601
  retryCount:     number;    // increments on each failed upload attempt
  status:         'pending' | 'uploading' | 'failed';
}

// ── READ ───────────────────────────────────────────────────────────────────────

export async function getQueue(): Promise<QueuedSession[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as QueuedSession[]) : [];
  } catch {
    return [];
  }
}

// ── WRITE ──────────────────────────────────────────────────────────────────────

export async function enqueueSession(
  session: Omit<QueuedSession, 'retryCount' | 'status'>,
): Promise<void> {
  const queue = await getQueue();
  const entry: QueuedSession = { ...session, retryCount: 0, status: 'pending' };
  const updated = [...queue, entry];
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(updated));
}

export async function updateQueueEntry(
  id: string,
  patch: Partial<Pick<QueuedSession, 'status' | 'retryCount'>>,
): Promise<void> {
  const queue = await getQueue();
  const updated = queue.map((s) => (s.id === id ? { ...s, ...patch } : s));
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(updated));
}

export async function dequeueSession(id: string): Promise<void> {
  const queue = await getQueue();
  const session = queue.find((s) => s.id === id);

  // Delete the video file from disk before removing from queue
  if (session) {
    await FileSystem.deleteAsync(session.videoUri, { idempotent: true });
  }

  const updated = queue.filter((s) => s.id !== id);
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(updated));
}

export async function getQueueCount(): Promise<number> {
  const q = await getQueue();
  return q.length;
}
```

---

#### JOB FE-T3-2: Create `src/cache/cacheKeys.ts` additions

Add the new queue key to the existing constants file:

```typescript
// src/cache/cacheKeys.ts — ADD to existing CACHE_KEYS object:

export const CACHE_KEYS = {
  SESSION_LIST:          'sc_session_list_v1',
  SESSION_DETAIL_PREFIX: 'sc_session_detail_v1_',
  CACHE_SCHEMA_VERSION:  'sc_cache_version',
  OFFLINE_QUEUE:         'sc_offline_queue_v1',   // ADD
} as const;
```

---

#### JOB FE-T3-3: Create `src/utils/queueDrain.ts`

The queue drain function is called both by the background task and by the foreground app (on connectivity restore). It must be safe to call from either context.

```typescript
// src/utils/queueDrain.ts

import NetInfo from '@react-native-community/netinfo';
import * as Notifications from 'expo-notifications';
import { getQueue, updateQueueEntry, dequeueSession } from '../cache/offlineQueue';
import { saveSession } from '../cache/sessionCache';
import { compressVideoFor480p } from './compressVideo';
import { OFFLINE_QUEUE } from '../theme/constants';
import apiClient from '../api/client';
import * as SecureStore from 'expo-secure-store';
import { EvaluationResult } from '../types/api';

export async function drainOfflineQueue(): Promise<void> {
  const netState = await NetInfo.fetch();
  if (!netState.isConnected) return; // No connectivity — do nothing

  const queue = await getQueue();
  const pending = queue.filter(
    (s) => s.status === 'pending' && s.retryCount < OFFLINE_QUEUE.RETRY_MAX,
  );

  for (const session of pending) {
    await updateQueueEntry(session.id, { status: 'uploading' });

    try {
      // Compress (may already be compressed — compressor is idempotent at 480p)
      const { uri } = await compressVideoFor480p(session.videoUri);

      // Build form
      const form = new FormData();
      form.append('video', { uri, name: 'session.mp4', type: 'video/mp4' } as any);

      const userRaw = await SecureStore.getItemAsync('auth_user');
      const user = userRaw ? JSON.parse(userRaw) : null;
      if (user?.id) form.append('user_id', user.id);

      // Upload
      const response = await apiClient.post<EvaluationResult>(
        '/analyze/full',
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );

      // Save result to local cache
      await saveSession(response.data, session.elapsedSeconds, session.topicTitle);

      // Send push notification
      await Notifications.scheduleNotificationAsync({
        content: {
          title: 'Coach\'s Report Ready',
          body: `Your ${session.topicTitle} session has been analysed.`,
          data: { sessionId: response.data.session_metadata.session_id },
        },
        trigger: null, // immediate
      });

      // Remove from queue and delete video file
      await dequeueSession(session.id);

    } catch (err) {
      const newRetry = session.retryCount + 1;
      if (newRetry >= OFFLINE_QUEUE.RETRY_MAX) {
        // Mark as permanently failed — user will see it in queue UI
        await updateQueueEntry(session.id, { status: 'failed', retryCount: newRetry });
      } else {
        await updateQueueEntry(session.id, { status: 'pending', retryCount: newRetry });
      }
      // Continue draining other sessions — one failure doesn't block the queue
    }
  }
}
```

---

#### JOB FE-T3-4: Register background task in `App.tsx`

The background task wakes up when the system allows it (typically after a network state change) and drains the queue.

```typescript
// App.tsx — ADD to root file

import * as TaskManager from 'expo-task-manager';
import * as BackgroundFetch from 'expo-background-fetch';
import { drainOfflineQueue } from './src/utils/queueDrain';
import { OFFLINE_QUEUE } from './src/theme/constants';

// Register OUTSIDE of any component (top-level):
TaskManager.defineTask(OFFLINE_QUEUE.BACKGROUND_TASK_NAME, async () => {
  try {
    await drainOfflineQueue();
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

// Inside App component, in useEffect on mount:
useEffect(() => {
  BackgroundFetch.registerTaskAsync(OFFLINE_QUEUE.BACKGROUND_TASK_NAME, {
    minimumInterval: 15 * 60, // 15 minutes minimum (OS enforced)
    stopOnTerminate: false,
    startOnBoot: true,
  }).catch(() => {
    // Background fetch not available on all devices — queue still drains in foreground
  });
}, []);
```

---

#### JOB FE-T3-5: Update `src/screens/RecordingScreen.tsx` — Stop flow with offline check

When the user taps Stop, detect connectivity. If offline, skip `ProcessingScreen` entirely, enqueue the video, and navigate back to Dashboard with a status banner.

```typescript
// RecordingScreen.tsx — update doStop() function

import NetInfo from '@react-native-community/netinfo';
import { enqueueSession, getQueueCount } from '../cache/offlineQueue';
import { OFFLINE_QUEUE } from '../theme/constants';
import { v4 as uuidv4 } from 'uuid';  // add: npm install uuid @types/uuid

async function doStop() {
  setRecordingMeta(elapsedSeconds, topicTitle);
  stopRecording();
  // videoUri appears asynchronously — handled in useEffect below
}

// Replace the existing videoUri useEffect:
useEffect(() => {
  if (state !== 'stopped' || !videoUri) return;

  (async () => {
    const net = await NetInfo.fetch();

    if (net.isConnected) {
      // ── Online: existing flow ──────────────────────────────────────────
      navigation.replace('Processing', { videoUri });
    } else {
      // ── Offline: queue the session ────────────────────────────────────
      const queueCount = await getQueueCount();

      if (queueCount >= OFFLINE_QUEUE.MAX_SESSIONS) {
        // Blocking alert — queue full
        Alert.alert(
          'Queue Full',
          `You have ${OFFLINE_QUEUE.MAX_SESSIONS} sessions waiting to upload. Connect to the internet to analyse them first.`,
          [{ text: 'OK' }],
        );
        return;
      }

      await enqueueSession({
        id:             uuidv4(),
        videoUri,
        topicTitle,
        elapsedSeconds,
        queuedAt:       new Date().toISOString(),
      });

      navigation.replace('Dashboard');
      // Dashboard will show a PendingQueueBanner (see FE-T3-6)
    }
  })();
}, [state, videoUri]);
```

**Add queue warning before recording starts** (in the `handleStop` function, before `doStop`):

```typescript
// Also add a pre-stop warning when recording and already at cap-1:
const queueCount = await getQueueCount();
if (queueCount >= OFFLINE_QUEUE.MAX_SESSIONS - 1) {
  // Warn: approaching limit
  Alert.alert(
    'Queue Nearly Full',
    `You have ${queueCount} session${queueCount > 1 ? 's' : ''} waiting to upload. Connect to upload before recording more.`,
    [
      { text: 'Keep Recording', style: 'cancel' },
      { text: 'Stop Anyway', onPress: doStop },
    ],
  );
  return;
}
```

---

#### JOB FE-T3-6: Create `src/components/dashboard/PendingQueueBanner.tsx`

A small persistent banner shown on the Dashboard when there are queued sessions. It drains the queue in the foreground when the user is online and on the Dashboard.

```typescript
// src/components/dashboard/PendingQueueBanner.tsx

import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { getQueueCount } from '../../cache/offlineQueue';
import { drainOfflineQueue } from '../../utils/queueDrain';
import { colors } from '../../theme/colors';
import { fonts, fontSize } from '../../theme/typography';
import { spacing } from '../../theme/spacing';

export const PendingQueueBanner: React.FC = () => {
  const [count,    setCount]    = useState(0);
  const [isOnline, setIsOnline] = useState(true);
  const [draining, setDraining] = useState(false);

  useEffect(() => {
    const refresh = async () => setCount(await getQueueCount());
    refresh();

    const unsub = NetInfo.addEventListener(async (state) => {
      setIsOnline(!!state.isConnected);
      if (state.isConnected) {
        // Came online — drain immediately in foreground
        setDraining(true);
        await drainOfflineQueue();
        await refresh();
        setDraining(false);
      }
    });
    return unsub;
  }, []);

  if (count === 0) return null;

  return (
    <View style={[styles.banner, isOnline ? styles.online : styles.offline]}>
      {draining ? (
        <>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={styles.text}>Uploading {count} queued session{count > 1 ? 's' : ''}…</Text>
        </>
      ) : (
        <>
          <Text style={styles.dot}>●</Text>
          <Text style={styles.text}>
            {count} session{count > 1 ? 's' : ''} waiting to upload
          </Text>
          <Text style={styles.hint}>{isOnline ? 'Uploading…' : 'Connect to upload'}</Text>
        </>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.base,
    paddingVertical: 10,
    borderRadius: 12,
    marginBottom: spacing.base,
    borderWidth: 0.5,
  },
  online:  { backgroundColor: 'rgba(17,82,212,0.12)', borderColor: 'rgba(17,82,212,0.3)' },
  offline: { backgroundColor: 'rgba(245,158,11,0.10)', borderColor: 'rgba(245,158,11,0.3)' },
  dot:  { fontSize: 8, color: colors.primary },
  text: { fontFamily: fonts.medium, fontSize: fontSize.sm, color: colors.textSecondary, flex: 1 },
  hint: { fontFamily: fonts.regular, fontSize: fontSize.xs, color: colors.textMuted },
});
```

**Add to DashboardScreen.tsx** (above the PerformanceGrid, below the StreakMilestoneTip):

```typescript
import { PendingQueueBanner } from '../components/dashboard/PendingQueueBanner';

// In JSX:
<PendingQueueBanner />
```

---

#### JOB FE-T3-7: Configure push notification permissions in `app.json` and `App.tsx`

```json
// app.json — add to plugins array:
["expo-notifications", {
  "icon": "./assets/notification-icon.png",
  "color": "#1152D4",
  "sounds": []
}]
```

```typescript
// App.tsx — request notification permission on first launch

import * as Notifications from 'expo-notifications';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

// In useEffect:
Notifications.requestPermissionsAsync().then(({ status }) => {
  if (status !== 'granted') {
    console.log('[Notifications] Permission not granted — queue notifications suppressed');
  }
});

// Handle notification tap (navigate to session detail):
const responseListener = Notifications.addNotificationResponseReceivedListener((response) => {
  const sessionId = response.notification.request.content.data?.sessionId;
  if (sessionId) {
    // Navigate to SessionDetail — requires a navigation ref accessible here
    navigationRef.current?.navigate('SessionDetail', { sessionId });
  }
});
```

---

## 5. New File Manifest

Files to create from scratch. All paths relative to `src/`.

| File | Owner | Task |
|------|-------|------|
| `theme/constants.ts` | Frontend | T1 + T2 + T3 |
| `store/streakStore.ts` | Frontend | T1 |
| `components/dashboard/StreakMilestoneTip.tsx` | Frontend | T1 |
| `components/dashboard/PendingQueueBanner.tsx` | Frontend | T3 |
| `components/ui/SessionActivityCard.tsx` | Frontend | T2 |
| `utils/shareCard.ts` | Frontend | T2 |
| `utils/queueDrain.ts` | Frontend | T3 |
| `cache/offlineQueue.ts` | Frontend | T3 |
| `streak/routes.py` *(backend)* | Backend | T1 |

> **Note — T1 QuoteCard gate:** No new file is created. The `<QuoteCard />` component and its daily-rotation logic already exist. All gating logic is added inline to `DashboardScreen.tsx` (JOB FE-T1-5).

---

## 6. Modified File Manifest

Files that already exist and need changes. Read the specific job numbers for exact diffs.

| File | Changes | Task | Job Ref |
|------|---------|------|---------|
| `src/types/cache.ts` | Add 3 skill score fields to `SessionListEntry` | T1 | FE-T1-2 |
| `src/cache/sessionCache.ts` | Populate new fields in `saveSession()` | T1 | FE-T1-2 |
| `src/cache/cacheKeys.ts` | Add `OFFLINE_QUEUE` key | T3 | FE-T3-2 |
| `src/screens/DashboardScreen.tsx` | Wire `useStreakStore`; add milestone tip card; add `QuoteCard` locked/unlocked gate with fade animation | T1 + T3 | FE-T1-4, FE-T1-5 |
| `src/screens/RecordingScreen.tsx` | Offline check in stop flow, queue cap warning | T3 | FE-T3-5 |
| `src/screens/ResultsScreen.tsx` | Off-screen card + share button | T2 | FE-T2-3 |
| `src/screens/SessionDetailScreen.tsx` | Same share card pattern | T2 | FE-T2-4 |
| `App.tsx` | Background task registration, notification handler | T3 | FE-T3-4, FE-T3-7 |
| `app.json` | expo-notifications plugin | T3 | FE-T3-7 |
| `backend/app.py` | Register `streak_bp` blueprint | T1 | BE-T1-1 |

---

## 7. Supabase Schema Additions

Run this migration in the Supabase SQL editor. One new table, one new index. Nothing else changes.

```sql
-- ── T1: Motivational tips table ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS motivational_tips (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  streak_milestone int NOT NULL CHECK (streak_milestone IN (3, 7, 14, 30)),
  skill_focus    text NOT NULL    CHECK (skill_focus IN ('confidence', 'clarity', 'engagement', 'nervousness', 'overall')),
  tip_text       text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Index for the query pattern: milestone + skill
CREATE INDEX IF NOT EXISTS idx_tips_milestone_skill
  ON motivational_tips (streak_milestone, skill_focus);

-- Row-level security: read-only for authenticated users
ALTER TABLE motivational_tips ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone authenticated can read tips"
  ON motivational_tips FOR SELECT
  TO authenticated
  USING (true);

-- ── Seed data — populate before launch ──────────────────────────────────────────

INSERT INTO motivational_tips (streak_milestone, skill_focus, tip_text) VALUES
  (3,  'confidence', 'Three sessions in a row — your voice is finding its footing. Confidence builds from repetition, not perfection.'),
  (3,  'clarity',    'Three days of focused practice. Your ideas are becoming cleaner with every session.'),
  (3,  'overall',    'You''ve shown up three days running. That consistency is the foundation of every great speaker.'),
  (7,  'confidence', 'A full week of consistent work. Your confidence baseline has shifted — you may not notice it yet, but your scores do.'),
  (7,  'overall',    'Seven sessions. Most people quit before day three. You didn''t.'),
  (14, 'overall',    'Two weeks of deliberate practice. You are in the top tier of users who reach this point.'),
  (30, 'overall',    'Thirty days. This is no longer a habit you''re building — it''s a skill you have.');

-- Add more rows per skill before launch. Aim for 5+ rows per milestone+skill combo.
```

---

## 8. Integration Order & Dependencies

Build in this order. Each task has dependencies on the previous.

```
Step 1 — Foundation (no dependencies, build first)
  ├── Create src/theme/constants.ts                   [FE-T1-1 prerequisite]
  ├── Update src/types/cache.ts                       [FE-T1-2]
  └── Update src/cache/sessionCache.ts               [FE-T1-2]

Step 2 — T1 Streak (depends on Step 1)
  ├── Create src/store/streakStore.ts                [FE-T1-1]
  ├── Create StreakMilestoneTip.tsx                   [FE-T1-3]
  ├── Update DashboardScreen.tsx — streak wiring      [FE-T1-4]
  ├── Update DashboardScreen.tsx — QuoteCard gate     [FE-T1-5]
  │     └── Depends on FE-T1-4 (uses hasCompletedTodaySession from streakStore)
  └── Backend: streak/routes.py + register blueprint [BE-T1-1]
        └── Run Supabase migration + seed data        [Section 7]

Step 3 — T2 Share Card (depends on Step 1, no T1 dependency)
  ├── Install react-native-view-shot + rebuild Dev Client
  ├── Create SessionActivityCard.tsx                  [FE-T2-1]
  ├── Create src/utils/shareCard.ts                  [FE-T2-2]
  ├── Update ResultsScreen.tsx                        [FE-T2-3]
  └── Update SessionDetailScreen.tsx                  [FE-T2-4]

Step 4 — T3 Offline Queue (depends on Step 1)
  ├── Install expo-network + expo-notifications + rebuild
  ├── Add OFFLINE_QUEUE key to cacheKeys.ts           [FE-T3-2]
  ├── Create src/cache/offlineQueue.ts               [FE-T3-1]
  ├── Create src/utils/queueDrain.ts                 [FE-T3-3]
  ├── Register background task in App.tsx             [FE-T3-4]
  ├── Update RecordingScreen.tsx                      [FE-T3-5]
  ├── Create PendingQueueBanner.tsx                   [FE-T3-6]
  └── Update app.json + notification config           [FE-T3-7]
```

---

## 9. Testing Checklist

### T1 — Streak Module

- [ ] Dashboard shows correct streak count after completing a session
- [ ] Streak count does NOT increment if two sessions are on the same calendar day
- [ ] Milestone tip card appears on the dashboard after completing the 3rd session
- [ ] Milestone tip card is dismissable and does not reappear for the same milestone
- [ ] `StreakSection` 4x2 grid colors match `scoreToStreakColor()` logic (>0.70 = bright green, 0.40–0.70 = mid green, <0.40 = dark green)
- [ ] Empty state: all 8 squares show `streakEmpty` color on a fresh install
- [ ] `/streak/tip` endpoint returns 200 with a tip or `{ tip_text: null }` — never 500
- [ ] **QuoteCard — locked state:** On a day with no session, `QuoteCard` renders with overlay visible and quote text at opacity 0.18 (illegible)
- [ ] **QuoteCard — locked state:** The lock overlay displays the play icon and "Complete today's session to unlock" label
- [ ] **QuoteCard — locked CTA:** Tapping anywhere on the locked card navigates to `RecordingScreen` with today's topic preloaded
- [ ] **QuoteCard — unlock:** Completing and saving a session today causes the overlay to fade out (600ms) when the user returns to Dashboard
- [ ] **QuoteCard — unlock:** After fade-out, `QuoteCard` is fully visible and interactive; the overlay accepts zero pointer events
- [ ] **QuoteCard — persistence:** App killed and relaunched on a day where a session was already completed — card renders immediately unlocked with no animation flash
- [ ] **QuoteCard — midnight reset:** At 12:00 AM the quote rotates AND the lock state resets (overlay reappears) — verify by mocking the date in tests
- [ ] **QuoteCard — no remount:** `QuoteCard` component does not unmount/remount when the lock state changes — daily-rotation timer must survive the state flip

### T2 — Share Card

- [ ] Share button appears on ResultsScreen
- [ ] Share button appears on SessionDetailScreen
- [ ] Tapping share generates a 1080×1080 image (verify dimensions in Files app)
- [ ] Native share sheet opens with the image
- [ ] Card displays correct: overall score, 4 metrics, LLM closing quote, topic title, date
- [ ] Long LLM quotes truncate cleanly (3 lines max) without overflowing the card
- [ ] Share works from both live results and cached history sessions
- [ ] No crash if `motivational_closing` is empty string

### T3 — Offline Queue

- [ ] Recording in airplane mode enqueues the session and returns to Dashboard
- [ ] `PendingQueueBanner` appears on Dashboard showing correct queued count
- [ ] Queue drains automatically when device reconnects to internet
- [ ] Push notification fires when a queued session finishes analysis
- [ ] Tapping the push notification navigates to `SessionDetailScreen` with correct `sessionId`
- [ ] Attempting to queue a 4th session shows the blocking alert
- [ ] Failed sessions (after 3 retries) show `status: 'failed'` — do not block other queue items
- [ ] Video files are deleted from device storage after successful upload
- [ ] Queue persists across app restarts (AsyncStorage survives kills)
- [ ] Background task registers without error on both iOS and Android

---

*End of specification — v1.1. Questions → raise in the team channel before starting implementation.*  
*v1.1 change summary: Added JOB FE-T1-5 (QuoteCard daily gate); updated `streakStore` state interface with `hasCompletedTodaySession`; added `checkTodaySession()` helper; updated DashboardScreen modified file entry; updated integration order Step 2; extended T1 testing checklist with 8 new cases.*
