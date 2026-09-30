from PIL import Image, ImageOps

# Approximate background removal for scanned signatures on light paper: pixels near-white
# become transparent, pixels near-black stay opaque, values in between fade proportionally.
# Not ML-based (no rembg/onnxruntime dependency) — good enough for ink-on-paper scans.
# Configurable since some scans need a different cutoff (too faint/too dark ink) or even
# have an inverted (dark background, light ink) source image.
DEFAULT_LIGHT_THRESHOLD = 225
DEFAULT_DARK_THRESHOLD = 60


def remove_background(image, light_threshold=DEFAULT_LIGHT_THRESHOLD, dark_threshold=DEFAULT_DARK_THRESHOLD, invert=False):
    image = image.convert('RGBA')
    gray = image.convert('L')
    if invert:
        gray = ImageOps.invert(gray)

    light_threshold = max(dark_threshold + 1, light_threshold)
    span = light_threshold - dark_threshold
    lut = []
    for value in range(256):
        if value >= light_threshold:
            lut.append(0)
        elif value <= dark_threshold:
            lut.append(255)
        else:
            lut.append(int(255 * (light_threshold - value) / span))

    alpha = gray.point(lut)
    image.putalpha(alpha)
    return image
