
dirs4 = [(-1,0),(1,0),(0,-1),(0,1)]
dirs8 = dirs4 + [(-1,-1),(-1,1),(1,-1),(1,1)]

ci4_palette = []
for i in range(16):
    v = i * 16
    ci4_palette.append(v)
    ci4_palette.append(v)
    ci4_palette.append(v)


def get(image, co, default):

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
