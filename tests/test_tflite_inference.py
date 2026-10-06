import unittest
import numpy as np
from inference.tflite_inference import rgb565_to_rgb888


class TfliteInputTests(unittest.TestCase):
    def test_little_endian_colors_and_bit_replication(self):
        pixels = np.array([0, 0xFFFF, 0xF800, 0x07E0, 0x001F, (17 << 11) | (33 << 5) | 9], dtype="<u2")
        actual = rgb565_to_rgb888(pixels.tobytes())
        np.testing.assert_array_equal(actual, [[0, 0, 0], [255, 255, 255], [255, 0, 0],
                                               [0, 255, 0], [0, 0, 255], [140, 134, 74]])
        self.assertEqual(actual.dtype, np.uint8)

    def test_truncated_pixel_is_rejected(self):
        with self.assertRaises(ValueError):
            rgb565_to_rgb888(b"\x00")
