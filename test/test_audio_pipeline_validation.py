import unittest

from audio.pipeline import _normalize_acoustic_windows, _normalize_device_acoustics


class AudioPipelineValidationTests(unittest.TestCase):
    def test_normalize_device_acoustics_clamps_values(self):
        result = _normalize_device_acoustics(
            {
                "pitch_variance_normalized": 1.5,
                "jitter_normalized": -0.1,
                "energy_variation_normalized": "0.45",
                "pause_ratio": 0.2,
            }
        )

        self.assertEqual(
            result,
            {
                "pitch_variance_normalized": 1.0,
                "jitter_normalized": 0.0,
                "energy_variation_normalized": 0.45,
                "pause_ratio": 0.2,
            },
        )

    def test_normalize_device_acoustics_rejects_non_finite_values(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            _normalize_device_acoustics(
                {
                    "pitch_variance_normalized": "nan",
                    "jitter_normalized": 0.1,
                    "energy_variation_normalized": 0.2,
                    "pause_ratio": 0.3,
                }
            )

    def test_normalize_acoustic_windows_deduplicates_and_sorts(self):
        result = _normalize_acoustic_windows(
            [
                {
                    "window_index": 2,
                    "time_start": 10.0,
                    "time_end": 15.0,
                    "pitch_variance_normalized": 0.6,
                    "pause_ratio": 0.2,
                },
                {
                    "window_index": 1,
                    "time_start": 5.0,
                    "time_end": 10.0,
                    "pitch_variance_normalized": 0.3,
                    "pause_ratio": 0.1,
                },
                {
                    "window_index": 2,
                    "time_start": 10.0,
                    "time_end": 15.0,
                    "pitch_variance_normalized": 0.8,
                    "pause_ratio": 0.4,
                },
            ]
        )

        self.assertEqual([window["window_index"] for window in result], [1, 2])
        self.assertEqual(result[1]["pitch_variance_normalized"], 0.8)
        self.assertEqual(result[1]["pause_ratio"], 0.4)

    def test_normalize_acoustic_windows_rejects_bad_ranges(self):
        with self.assertRaisesRegex(ValueError, "time_end > time_start"):
            _normalize_acoustic_windows(
                [
                    {
                        "window_index": 0,
                        "time_start": 5.0,
                        "time_end": 5.0,
                        "pitch_variance_normalized": 0.3,
                        "pause_ratio": 0.1,
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
