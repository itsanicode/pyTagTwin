# -*- coding: utf-8 -*-
"""Draw the ribbon icons for the Tag Twin buttons.

Run it to regenerate every ``icon.png`` in the extension::

    python make_icons.py

Everything is drawn analytically and supersampled, so there is no image library
to install and no binary asset anyone has to open a paint program to edit.
"""

from __future__ import division, print_function

import math
import os
import struct
import zlib

SIZE = 96
SUPERSAMPLE = 3

INK = (0x33, 0x41, 0x55, 255)        # dark slate - frames and leaders
BLUE = (0x1E, 0x88, 0xE5, 255)       # the source annotation
ORANGE = (0xF5, 0x7C, 0x00, 255)     # the copy, and the action
GREY = (0xB0, 0xBE, 0xC5, 255)       # things that are only context

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, os.pardir, 'Tag Twin.tab', 'Replicate.panel')


class Canvas(object):
    """A supersampled RGBA canvas addressed in final-image coordinates."""

    def __init__(self, size=SIZE, factor=SUPERSAMPLE):
        self.size = size
        self.factor = factor
        self.width = size * factor
        self.pixels = [[(0, 0, 0, 0)] * self.width for _ in range(self.width)]

    # -- primitives -------------------------------------------------------

    def _blend(self, x, y, colour):
        if x < 0 or y < 0 or x >= self.width or y >= self.width:
            return
        source_alpha = colour[3] / 255.0
        if source_alpha <= 0.0:
            return
        existing = self.pixels[y][x]
        if source_alpha >= 1.0:
            self.pixels[y][x] = colour
            return
        out = []
        for channel in range(3):
            out.append(int(round(colour[channel] * source_alpha
                                 + existing[channel] * (1.0 - source_alpha))))
        out.append(max(existing[3], colour[3]))
        self.pixels[y][x] = tuple(out)

    def _paint(self, inside, colour, bounds=None):
        """Fill every device pixel whose centre satisfies ``inside``."""
        factor = self.factor
        if bounds is None:
            x0 = y0 = 0
            x1 = y1 = self.size
        else:
            x0, y0, x1, y1 = bounds
        px0 = max(0, int(math.floor(x0 * factor)))
        py0 = max(0, int(math.floor(y0 * factor)))
        px1 = min(self.width, int(math.ceil(x1 * factor)) + 1)
        py1 = min(self.width, int(math.ceil(y1 * factor)) + 1)
        for py in range(py0, py1):
            y = (py + 0.5) / factor
            for px in range(px0, px1):
                x = (px + 0.5) / factor
                if inside(x, y):
                    self._blend(px, py, colour)

    def rectangle(self, x0, y0, x1, y1, colour, radius=0.0):
        def inside(x, y):
            if radius <= 0.0:
                return x0 <= x <= x1 and y0 <= y <= y1
            cx = min(max(x, x0 + radius), x1 - radius)
            cy = min(max(y, y0 + radius), y1 - radius)
            return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
        self._paint(inside, colour, (x0 - 1, y0 - 1, x1 + 1, y1 + 1))

    def frame(self, x0, y0, x1, y1, colour, width, radius=0.0):
        def inside(x, y):
            def hit(rx0, ry0, rx1, ry1):
                if radius <= 0.0:
                    return rx0 <= x <= rx1 and ry0 <= y <= ry1
                cx = min(max(x, rx0 + radius), rx1 - radius)
                cy = min(max(y, ry0 + radius), ry1 - radius)
                return (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius
            return hit(x0, y0, x1, y1) and not hit(
                x0 + width, y0 + width, x1 - width, y1 - width)
        self._paint(inside, colour, (x0 - 1, y0 - 1, x1 + 1, y1 + 1))

    def line(self, start, end, colour, width):
        (ax, ay), (bx, by) = start, end
        dx, dy = bx - ax, by - ay
        span = dx * dx + dy * dy
        half = width / 2.0

        def inside(x, y):
            if span <= 0.0:
                return (x - ax) ** 2 + (y - ay) ** 2 <= half * half
            t = ((x - ax) * dx + (y - ay) * dy) / span
            t = min(max(t, 0.0), 1.0)
            ex = x - (ax + t * dx)
            ey = y - (ay + t * dy)
            return ex * ex + ey * ey <= half * half
        self._paint(inside, colour,
                    (min(ax, bx) - width, min(ay, by) - width,
                     max(ax, bx) + width, max(ay, by) + width))

    def disc(self, cx, cy, radius, colour):
        self._paint(lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius,
                    colour, (cx - radius - 1, cy - radius - 1,
                             cx + radius + 1, cy + radius + 1))

    def ring(self, cx, cy, radius, width, colour):
        outer = radius + width / 2.0
        inner = radius - width / 2.0

        def inside(x, y):
            distance = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            return inner <= distance <= outer
        self._paint(inside, colour, (cx - outer - 1, cy - outer - 1,
                                     cx + outer + 1, cy + outer + 1))

    def triangle(self, points, colour):
        (ax, ay), (bx, by), (cx, cy) = points

        def side(px, py, x0, y0, x1, y1):
            return (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)

        def inside(x, y):
            d1 = side(x, y, ax, ay, bx, by)
            d2 = side(x, y, bx, by, cx, cy)
            d3 = side(x, y, cx, cy, ax, ay)
            return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))
        xs = [ax, bx, cx]
        ys = [ay, by, cy]
        self._paint(inside, colour,
                    (min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1))

    def gear(self, cx, cy, outer, body, hole, teeth, colour):
        def inside(x, y):
            dx, dy = x - cx, y - cy
            distance = math.sqrt(dx * dx + dy * dy)
            if distance < hole:
                return False
            if distance <= body:
                return True
            return distance <= outer and math.cos(teeth * math.atan2(dy, dx)) > 0.35
        self._paint(inside, colour, (cx - outer - 1, cy - outer - 1,
                                     cx + outer + 1, cy + outer + 1))

    # -- output -----------------------------------------------------------

    def downsampled(self):
        factor = self.factor
        rows = []
        for y in range(self.size):
            row = bytearray()
            for x in range(self.size):
                totals = [0, 0, 0, 0]
                for sy in range(factor):
                    line = self.pixels[y * factor + sy]
                    for sx in range(factor):
                        pixel = line[x * factor + sx]
                        alpha = pixel[3]
                        for channel in range(3):
                            totals[channel] += pixel[channel] * alpha
                        totals[3] += alpha
                count = factor * factor
                alpha = totals[3] / count
                if totals[3] > 0:
                    row += bytes(bytearray(
                        [int(round(totals[c] / totals[3])) for c in range(3)]))
                else:
                    row += b'\x00\x00\x00'
                row += bytes(bytearray([int(round(alpha))]))
            rows.append(bytes(row))
        return rows

    def save(self, path):
        write_png(path, self.size, self.size, self.downsampled())

    def preview(self):
        """Coarse ASCII rendering, so the shapes can be checked without a viewer."""
        rows = self.downsampled()
        step = max(1, self.size // 32)
        ramp = ' .:-=+*#%@'
        lines = []
        for y in range(0, self.size, step):
            line = []
            for x in range(0, self.size, step):
                alpha = rows[y][x * 4 + 3]
                line.append(ramp[min(len(ramp) - 1, alpha * len(ramp) // 256)])
            lines.append(''.join(line))
        return '\n'.join(lines)


def write_png(path, width, height, rows):
    raw = b''.join(b'\x00' + row for row in rows)

    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack('>I', len(payload)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    data = (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))
    with open(path, 'wb') as handle:
        handle.write(data)


# --------------------------------------------------------------------------
# the icons
# --------------------------------------------------------------------------

def _view_frame(canvas, x, colour=INK, width=3.0):
    canvas.frame(x, 14, x + 34, 82, colour, width, radius=4.0)


def _tag(canvas, x, colour, leader=True):
    """A leader from an element dot up into a label - a tag, in miniature."""
    if leader:
        canvas.disc(x + 9, 68, 3.5, INK)
        canvas.line((x + 9, 68), (x + 15, 54), INK, 2.4)
    canvas.rectangle(x + 11, 30, x + 30, 52, colour, radius=2.5)


def icon_replicate():
    canvas = Canvas()
    _view_frame(canvas, 3, GREY)
    _view_frame(canvas, 59, INK)
    _tag(canvas, 3, BLUE)
    _tag(canvas, 59, BLUE)
    # the arrow carrying one across to the other
    canvas.line((40, 48), (49, 48), ORANGE, 6.0)
    canvas.triangle([(47, 40), (47, 56), (56, 48)], ORANGE)
    return canvas


def icon_preview():
    canvas = Canvas()
    _view_frame(canvas, 3, GREY)
    _view_frame(canvas, 59, GREY)
    _tag(canvas, 3, GREY, leader=False)
    _tag(canvas, 59, GREY, leader=False)
    # a magnifier over the join, looking at how well the two agree
    canvas.disc(48, 43, 15.0, (255, 255, 255, 70))
    canvas.ring(48, 43, 18, 6.0, INK)
    canvas.line((61, 56), (77, 76), ORANGE, 8.5)
    return canvas


def icon_find_identical():
    canvas = Canvas()
    positions = [(x, y) for y in (10, 38, 66) for x in (10, 38, 66)]
    highlighted = {0, 4, 8}
    for index, (x, y) in enumerate(positions):
        colour = BLUE if index in highlighted else GREY
        canvas.rectangle(x, y, x + 20, y + 20, colour, radius=3.0)
    return canvas


def icon_settings():
    canvas = Canvas()
    canvas.gear(48, 48, 40, 30, 13, 8, INK)
    canvas.ring(48, 48, 18, 4.0, ORANGE)
    return canvas


def icon_tag_like_view():
    """A tagged frame on the left setting the position for the one on the right."""
    canvas = Canvas()
    _view_frame(canvas, 3, GREY)
    _view_frame(canvas, 59, INK)
    _tag(canvas, 3, GREY)
    # the target: the same tag, snapped onto a dashed guide at the same offset
    canvas.disc(68, 68, 3.5, INK)
    canvas.line((68, 68), (74, 54), INK, 2.4)
    canvas.rectangle(70, 30, 89, 52, ORANGE, radius=2.5)
    for y in range(30, 53, 7):
        canvas.line((62, y), (67, y), GREY, 2.0)
    return canvas


ICONS = (
    ('Replicate Annotations', icon_replicate),
    ('Preview Match', icon_preview),
    ('Find Identical', icon_find_identical),
    ('Tag Like View', icon_tag_like_view),
    ('Settings', icon_settings),
)


def main(preview=False):
    for name, maker in ICONS:
        canvas = maker()
        path = os.path.join(PANEL, name + '.pushbutton', 'icon.png')
        canvas.save(path)
        print('wrote {0} ({1} bytes)'.format(
            os.path.relpath(path, HERE), os.path.getsize(path)))
        if preview:
            print(canvas.preview())
            print('')


if __name__ == '__main__':
    import sys
    main(preview='--preview' in sys.argv)
