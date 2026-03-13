import numpy as np
import math
from typing import Optional

class OneEuroFilter:
    """
    A NumPy-vectorized implementation of the One Euro Filter.
    Designed for smoothing MediaPipe landmarks (shape: [33, 4]).
    """
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev: Optional[np.ndarray] = None
        self.dx_prev: Optional[np.ndarray] = None
        self.t_prev: Optional[float] = None

    def _smoothing_factor(self, t_e: float, cutoff: np.ndarray) -> np.ndarray:
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

    def __call__(self, x: np.ndarray, timestamp: float) -> np.ndarray:
        """
        Filters the input landmarks.
        :param x: Current landmarks array (e.g., shape [33, 4])
        :param timestamp: Current frame timestamp in seconds
        """
        if self.t_prev is None:
            self.x_prev = x.copy()
            self.dx_prev = np.zeros_like(x)
            self.t_prev = timestamp
            return x

        t_e = timestamp - self.t_prev
        if t_e <= 0:
            return self.x_prev

        # 1. Filter the derivative to get the speed
        # Using a scalar d_cutoff for simplicity on derivative
        a_d = (2 * math.pi * self.d_cutoff * t_e) / (2 * math.pi * self.d_cutoff * t_e + 1)
        dx = (x - self.x_prev) / t_e
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev

        # 2. Compute adaptive cutoff based on speed
        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        
        # 3. Filter the signal
        a = self._smoothing_factor(t_e, cutoff)
        x_hat = a * x + (1 - a) * self.x_prev

        # Update state
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = timestamp

        return x_hat
