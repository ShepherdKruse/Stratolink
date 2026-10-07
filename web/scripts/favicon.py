"""Build the globe's static icons and rotation sheet. Requires Pillow."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / 'reference/favicon/land-110m.json').read_text())
OUTPUT = ROOT / 'public/assets/favicon'
OUTPUT.mkdir(parents=True, exist_ok=True)
SCALE, SHIFT = DATA['transform']['scale'], DATA['transform']['translate']
arcs = []
for arc in DATA['arcs']:
    x = y = 0
    points = []
    for dx, dy in arc:
        x += dx
        y += dy
        points.append((x * SCALE[0] + SHIFT[0], y * SCALE[1] + SHIFT[1]))
    arcs.append(points)

mask = Image.new('L', (1440, 720))
draw = ImageDraw.Draw(mask)
for geometry in DATA['objects']['land']['geometries']:
    polygons = geometry['arcs'] if geometry['type'] == 'MultiPolygon' else [geometry['arcs']]
    for polygon in polygons:
        for i, ring in enumerate(polygon):
            points = []
            for index in ring:
                points.extend(arcs[index] if index >= 0 else list(reversed(arcs[~index])))
            draw.polygon([((lon + 180) * 4, (90 - lat) * 4) for lon, lat in points], fill=255 if i == 0 else 0)
land = mask.load()
shelf = mask.filter(ImageFilter.GaussianBlur(5)).load()

# Orthographic globe: tilt and color family match the light footer map.
SIZE, FRAMES, COLUMNS = 128, 96, 12
phi = math.radians(25)
pixels = []
for py in range(SIZE):
    y = (SIZE / 2 - py - .5) / (SIZE * .47)
    for px in range(SIZE):
        x = (px + .5 - SIZE / 2) / (SIZE * .47)
        if x*x + y*y >= 1:
            continue
        z = math.sqrt(1 - x*x - y*y)
        lat = math.asin(y * math.cos(phi) + z * math.sin(phi))
        lon = math.atan2(x, z * math.cos(phi) - y * math.sin(phi))
        light = .76 + .24 * max(0, -.25*x + .35*y + .902*z)
        pixels.append((px, py, lon, lat, light))

def globe(degrees):
    image = Image.new('RGBA', (SIZE, SIZE))
    target = image.load()
    for px, py, lon, lat, light in pixels:
        mx = int(((math.degrees(lon) + degrees + 180) % 360) * 4) % 1440
        my = min(719, max(0, int((90 - math.degrees(lat)) * 4)))
        if land[mx, my] > 127:
            color = (246, 246, 242)
        else:
            coast = shelf[mx, my] / 255
            color = (157 + 47*coast, 184 + 33*coast, 197 + 25*coast)
        target[px, py] = (*[round(channel * light) for channel in color], 255)
    return image

sheet = Image.new('RGBA', (32*COLUMNS, 32*(FRAMES//COLUMNS)))
for frame in range(FRAMES):
    image = globe(-55 + 360*frame/FRAMES)
    sheet.paste(image.resize((32,32), Image.Resampling.LANCZOS), ((frame % COLUMNS)*32, (frame // COLUMNS)*32))
    if frame == 0:
        image.resize((64,64), Image.Resampling.LANCZOS).save(OUTPUT / 'globe.png', optimize=True)
        image.save(ROOT / 'public/favicon.ico', sizes=[(16,16),(32,32),(48,48),(64,64)])
        image.resize((180,180), Image.Resampling.LANCZOS).save(OUTPUT / 'apple-touch-icon.png', optimize=True)
sheet.save(OUTPUT / 'globe-frames.png', optimize=True)
print('Built 96 globe frames, static PNG, ICO and touch icon.')
