import PIL.Image

from . import image_utils
from . import minimap_utils
from . import z64c

from .scene_map import MapCamera, Image
from .utils import *

class OverworldMinimap:
    '''
    The minimap for an overworld scene. Unlike dungeon minimaps, there
    is only a single minimap per scene.
    '''
    def __init__(self, scene_map):
        self.scene_map = scene_map
        self.scene = scene_map.scene
        self.index = self.scene_map.overworld_index
        assert self.index is not None

        # Let's just center the scene in the minimap. Maybe make
        # this customizable later.
        bounds = self.scene.bounds
        cam_pos = Vec3(bounds.center.x, bounds.center.y, 0)

        # Every scene gets to set its own scale. Hyrule Field is the
        # most zoomed-out at 25:1. Zora's Domain and Goron City are
        # tied for the most zoomed-in at 5:1.

        # A couple of the maps are squashed by having different X and
        # Y scales; the Sacred Forest Meadow is 5:1 horizontally and
        # 7:1 vertically. Karariko is 7:1 and 6:1. For now let's
        # just support isotropic scaling.
        size = max(bounds.x.size, bounds.y.size) * 1.2
        cam_scale = round(size)

        # Unlike dungeon minimaps, overworld minimaps are not all the
        # same size.
        #
        # Vanilla OOT only uses widths 48, 64, 80 and 96, which are
        # equal to 16 * (3, 4, 5, 6). This is probably to ensure
        # alignment in the ROM.
        #
        # Heights are more varied, and it seems anything goes:
        # 39, 56, 58, 59, 62, 64, 65, 68, 72, 73, 78, 81, 85.
        #
        # The largest minimap is 96x85, which is the same size as all
        # the dungeon minimaps. Let's render at 96x85, and trim down
        # in postprocessing.
        render_size = Vec2(96, 85)
        
        self.camera = MapCamera(
            cam_pos,
            cam_scale,
            resolution=render_size,
            collection=None,
            image=Image(key=('miniraw', 'ow', self.index))
        )

        self.final_image = Image(key=('minimap', 'ow', self.index))


    @cached_property
    def diffs(self):
        # - sOwMinimapTexOffset
        # - sOwMinimapTexSize
        # These tell the game where the texture is so it can load it. We need
        # to rewrite the offset array because we might have shifted the other
        # maps around if we changed this map's size.
        num_pixels = self.minimap_size[0] * self.minimap_size[1]
        num_bytes = num_pixels // 2 # It's a 4bpp image.
        assert num_bytes % 8 == 0

        sOwMinimapTexSize = z64c.read_array(
            app.scene.oot_dir,
            'src/code/z_map_data.c',
            'sOwMinimapTexSize'
        )
        sOwMinimapTexSize[self.index] = num_bytes
        sOwMinimapTexOffset = [
            sum(sOwMinimapTexSize[0:i])
            for i in range(24)
        ]
        yield z64c.CArray(
            'src/code/z_map_data.c',
            'sOwMinimapTexOffset',
            [
                '0x%04X' % x
                for x in sOwMinimapTexOffset
            ]
        )
        yield z64c.CArray(
            'src/code/z_map_data.c',
            'sOwMinimapTexSize',
            sOwMinimapTexSize
        )

        # Minimap size in pixels
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwMinimapWidth',
            self.index,
            self.minimap_size[0]
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwMinimapHeight',
            self.index,
            self.minimap_size[1]
        )

        # Position to draw the minimap on the screen. We use a 
        # simple formula here, where x + w = 298 and y + h = 222,
        # but this isn't quite accurate. In original OOT, a bunch
        # of the maps are a few pixels out from these locations.
        # They were probably adjusted manually.
        minimap_pos = (
            298 - self.minimap_size[0],
            222 - self.minimap_size[1]
        )
            
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwMinimapPosX',
            self.index,
            minimap_pos[0]
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwMinimapPosY',
            self.index,
            minimap_pos[1]
        )

        # TODO: We don't support entrance icons yet
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwEntranceIconPosX',
            self.index,
            1,
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwEntranceIconPosY',
            self.index,
            0,
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwEntranceFlag',
            self.index,
            '0xFFFF',
        )

        # Compass data
        transform = minimap_utils.get_world_to_compass_mark_transform(
            minimap_pos,
            Vec2(self.minimap_size[0], self.minimap_size[1]),
            self.camera.camera_pos,
            self.camera.camera_scale,
            self.shift
        )
        compass_offset_x = int(round(transform[0][2]))
        compass_offset_y = int(round(transform[1][2]))
        scale_x_recip = round(1 / transform[0][0])
        scale_y_recip = round(1 / transform[0][0])

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sOwCompassInfo',
            self.index,
            [scale_x_recip, scale_y_recip, compass_offset_x, compass_offset_y]
        )
        
        # Install our finished minimap texture into the OOT assets
        # directory.
        map_grand_static_png = (
            f'assets/textures/map_grand_static/'
            f'_custom_scene{self.index}.ia4.png'
        )
        yield z64c.InstallFile(
            from_path=self.final_image.render_path,
            to_path=map_grand_static_png
        )

        # ZAPD will create an .inc.c file from the PNG when we build
        # OOT. Include it in the map_grand_static file.
        map_grand_static_include = map_grand_static_png.replace('.png', '.inc.c')
        yield z64c.ReplaceIncludes(
            path='assets/textures/map_grand_static/map_grand_static.c',
            names=[f'gScene{self.index}MinimapTex'],
            includes=[map_grand_static_include],
            first_index=self.index
        )

    def render_all(self):
        log("Render OVERWORLD MINIMAP camera")
        self.scene_map.render_map_camera(self.camera)

        self.minimap_size, self.shift = process_image(
            self.camera.image.render_path,
            self.final_image.render_path
        )


def process_image(raw_path, processed_path):
    """
    Take a raw camera render and turn it into a stylized
    map for use in the game.

    This is only for overworld minimaps; dungeon minimaps
    are different enough that they have their own function.
    """
    raw_rgba = PIL.Image.open(raw_path)
    raw_surface, _, _, raw_alpha = raw_rgba.split()
    out_image = PIL.Image.new('P', raw_alpha.size)
    out_image.putpalette(image_utils.ia4_palette, 'RGBA')

    w, h = out_image.size

    pix_wall = image_utils.ia4(7, 1)
    pix_ground = image_utils.ia4(3, 1)
    pix_outline = image_utils.ia4(0, 1)
    pix_oob = image_utils.ia4(0, 0)

    # Fill & first outline
    for y in range(h):
        for x in range(w):
            p = (x, y)
            in_alpha = raw_alpha.getpixel(p)
            if in_alpha == 0:
                if any(
                    image_utils.get(raw_alpha, (x+dx, y+dy), 0) != 0
                    for (dx, dy) in image_utils.dirs8
                ):
                    out_image.putpixel(p, pix_wall)
            else:
                out_image.putpixel(p, pix_ground)

    # Second outline with boxy shadow
    for y in range(h):
        for x in range(w):
            p = (x, y)
            pixel = out_image.getpixel(p)
            if pixel == pix_oob:
                if any(
                    image_utils.get(out_image, (x+dx, y+dy), pix_oob) in [pix_wall, pix_ground]
                    for (dx, dy) in image_utils.dirs8 + [
                            (-2, 0), (-2, 1), (-2, -1),
                            (0, -2), (1, -2), (-1, -2)
                    ]
                ):
                    out_image.putpixel(p, pix_outline)

    # Find bounds
    x0 = None
    y0 = None
    x1 = None
    y1 = None
    for y in range(h):
        for x in range(w):
            p = (x, y)
            pixel = out_image.getpixel(p)
            if pixel != pix_oob:
                if x0 is None or p[0] < x0: x0 = p[0]
                if x1 is None or p[0] > x1: x1 = p[0]
                if y0 is None or p[1] < y0: y0 = p[1]
                if y1 is None or p[1] > y1: y1 = p[1]

    if x0 is None:
        # Empty image
        shift = mathutils.Vector((0, 0))

    else:
        bounds = Rect.bounding_points(
            Vec2(x0, y0),
            Vec2(x1, y1)
        )

        # All maps have widths as a multiple of 16. Probably required
        # for alignment, so let's do it.
        x_error = bounds.size.x % 16
        if x_error:
            x_error = 16 - x_error
            xl = x_error // 2
            xr = x_error - xl
            bounds.origin.x -= xl
            bounds.size.x += xl + xr

        assert bounds.size.x % 16 == 0
        assert 0 <= bounds.size.x <= 96


        print('crop to', bounds)
        out_image = out_image.crop((
            bounds.min.x, bounds.min.y, bounds.max.x, bounds.max.y
        ))

        shift = mathutils.Vector((
            0,0
        ))
            

        # Shift to lower-right
        #shift_x = w - 2 - bounds.max.x
        #shift_y = h - 2 - bounds.max.y

        #shift = mathutils.Vector((shift_x, shift_y))

        #out_image = out_image.transform(
        #    (w, h),
        #    PIL.Image.AFFINE,
        #    (1, 0, -shift_x,
        #        0, 1, -shift_y),
        #    fillcolor=0
        #)


    out_image = out_image.convert('RGBA')
    out_image.save(processed_path)

    return out_image.size, shift
