# -*- coding: utf-8 -*-
"""The committed icons must be the ones ``tools/make_icons.py`` draws.

Comparing the *decompressed* pixel data rather than the file bytes keeps this
from failing just because a different zlib packed the same image differently.
"""

from __future__ import division

import os
import struct
import zlib

import make_icons

CASES = []


def case(func):
    CASES.append(func)
    return func


def read_png(path):
    """``(width, height, raw scanlines)`` for a PNG written by make_icons."""
    with open(path, 'rb') as handle:
        data = handle.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG: {0}'.format(path)
    position = 8
    compressed = b''
    header = None
    while position < len(data):
        length = struct.unpack('>I', data[position:position + 4])[0]
        tag = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        crc = struct.unpack('>I', data[position + 8 + length:position + 12 + length])[0]
        assert crc == zlib.crc32(tag + payload) & 0xFFFFFFFF, \
            'corrupt {0} chunk in {1}'.format(tag, path)
        if tag == b'IHDR':
            header = struct.unpack('>IIBBBBB', payload)
        elif tag == b'IDAT':
            compressed += payload
        position += 12 + length
    assert header is not None, 'no IHDR in {0}'.format(path)
    width, height, depth, colour = header[0], header[1], header[2], header[3]
    assert (depth, colour) == (8, 6), 'expected 8-bit RGBA, got {0}'.format(header)
    return width, height, zlib.decompress(compressed)


@case
def test_every_button_icon_matches_its_generator():
    for name, maker in make_icons.ICONS:
        path = os.path.join(make_icons.PANEL, name + '.pushbutton', 'icon.png')
        assert os.path.isfile(path), 'missing icon for {0}'.format(name)
        width, height, actual = read_png(path)
        assert (width, height) == (make_icons.SIZE, make_icons.SIZE)
        expected = b''.join(b'\x00' + row for row in maker().downsampled())
        assert actual == expected, (
            '{0}/icon.png differs from what make_icons.py draws - '
            'run "python tools/make_icons.py"'.format(name))


@case
def test_icons_are_actually_drawn_on():
    """A blank icon would pass a byte comparison against a blank generator."""
    for name, _ in make_icons.ICONS:
        path = os.path.join(make_icons.PANEL, name + '.pushbutton', 'icon.png')
        width, height, raw = read_png(path)
        stride = 1 + width * 4
        opaque = 0
        for row in range(height):
            base = row * stride + 1
            for column in range(width):
                if raw[base + column * 4 + 3] > 128:
                    opaque += 1
        share = opaque / float(width * height)
        assert 0.1 < share < 0.85, \
            '{0}: {1:.0%} of the icon is inked - it is blank or a solid block'.format(
                name, share)
