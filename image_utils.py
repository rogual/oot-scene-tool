
dirs4 = [(-1,0),(1,0),(0,-1),(0,1)]
dirs8 = dirs4 + [(-1,-1),(-1,1),(1,-1),(1,1)]

ci4_palette = []
for index in range(16):
    v = index * 16
    ci4_palette.extend([v, v, v])

ia4_palette = []
for index in range(16):
    i = index >> 1
    a = index & 1

    r = g = b = i * 32
    a = a * 255
    ia4_palette.extend([r, g, b, a])


def ia4(i, a):
    return (i << 1) | a


def get(image, co, default):
    """Like image.getpixel, but returns default if sampled OOB."""

    if co[0] < 0: return default
    if co[1] < 0: return default

    if co[0] >= image.width: return default
    if co[1] >= image.height: return default

    return image.getpixel(co)


def fast_outline(image, outline_color):
    """outline_color must not already exist in image."""
    for y in range(image.height):
        for x in range(image.width):
            if get(image, (x, y), 0) == 0:
                if any(
                    get(image, (x+dx, y+dy), 0) not in [0, outline_color]
                    for (dx, dy) in dirs8
                ):
                    image.putpixel((x, y), outline_color)
