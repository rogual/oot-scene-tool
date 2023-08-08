from dataclasses import dataclass

import itertools

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFilter

from . import app
from . import image_utils
from . import z64c

from .scene_map import MapCamera, Image
from .utils import *


@dataclass
class DungeonMinimapPage:
    '''
    One page of the dungeon minimap is displayed on-screen at a time.
    A room has one or more pages depending on how many floors it spans.
    '''
    layer: object
    camera: object
    final_image: object
    shift: mathutils.Vector = mathutils.Vector((0, 0))


class DungeonMinimap:
    '''
    The minimap for a dungeon. Contains a complete set of minimap pages.
    '''
    def __init__(self, scene_map):
        self.scene_map = scene_map
        self.scene = scene_map.scene

    @cached_property
    @yield_list
    def diffs(self):
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sDgnMinimapCount',
            self.scene.index,
            len(self.pages)
        )

        # All tex index offsets could potentially need to change.
        # Recalculate them from the minimap counts.
        sDgnMinimapCount = z64c.read_array(
            app.scene.oot_dir,
            'src/code/z_map_data.c',
            'sDgnMinimapCount'
        )
        sDgnMinimapCount[self.scene.index] = len(self.pages)
        sDgnMinimapTexIndexOffset = [
            sum(sDgnMinimapCount[0:i])
            for i in range(10)
        ]
        yield z64c.CArray(
            'src/code/z_map_data.c',
            'sDgnMinimapTexIndexOffset',
            sDgnMinimapTexIndexOffset
        )

        # Output world-to-compass-mark transforms. These tell OOT
        # how to transform objects' world positions to draw the
        # red and yellow compass arrows.
        transforms = [
            get_world_to_compass_mark_transform(
                page.camera.camera_pos,
                page.camera.camera_scale,
                page.shift
            )
            for page in self.pages
        ]

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sRoomCompassOffsetX',
            self.scene.index,
            [
                int(round(transform[0][2]))
                for transform in transforms
            ]
        )

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sRoomCompassOffsetY',
            self.scene.index,
            [
                int(round(transform[1][2]))
                for transform in transforms
            ]
        )

        # All rooms must share the same scale.  This is actually a
        # 4-array, the last two elements being an offset, but the
        # offset seems unsed; room offsets in sRoomCompassOffsetX/Y
        # are used instead.
        first_transform = transforms[0]
        scale_x_recip = round(1 / first_transform[0][0])
        scale_y_recip = round(1 / first_transform[1][1] * -1)

        for tr in transforms:
            assert tr[0][0] == first_transform[0][0]
            assert tr[1][1] == first_transform[1][1]

        if scale_x_recip == 0 or scale_y_recip == 0:
            raise Exception(
                "Compass scale is zero; ROM will crash."
            )

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sDgnCompassInfo',
            self.scene.index,
            [
                int(scale_x_recip),
                int(scale_y_recip),
            ]
        )

        # MAP MARKS
        gMapMarkDataTable = z64c.read_array(
            app.scene.oot_dir,
            'src/overlays/misc/ovl_map_mark_data/z_map_mark_data.c',
            'gMapMarkDataTable'
        )
        map_mark_array_name = gMapMarkDataTable[self.scene.index]

        map_mark_data = []
        
        for transform, page in zip(transforms, self.pages):
            room = page.layer.room

            page_mark_data = []
            map_mark_data.append(page_mark_data)

            chest_mark_data = []

            transform = get_world_to_96x85_minimap_transform(
                page.camera.camera_pos,
                page.camera.camera_scale,
                page.shift
            )

            for chest_flag, oot_pos in self.scene_map.chests(page.layer.actors):
                mark_pos = transform @ mathutils.Vector((
                    oot_pos.x,
                    oot_pos.z,
                    1
                ))

                # -4 because we're outputting the coords for the
                # top-left of each 8x8 chest icon
                chest_mark_data.append([
                    chest_flag,
                    int(round(mark_pos.x)) - 4,
                    int(round(mark_pos.y)) - 4
                ])


            if chest_mark_data:
                page_mark_data.append([
                    'MAP_MARK_CHEST',
                    len(chest_mark_data),
                    chest_mark_data
                ])

            page_mark_data.append(['MAP_MARK_NONE', 0, [0]])

        yield z64c.CArray(
            'src/overlays/misc/ovl_map_mark_data/z_map_mark_data.c',
            map_mark_array_name,
            map_mark_data
        )


        # LAYER SWITCHING
        # A room that spans several floors can have one minimap page
        # per floor. OOT will load the lowest page when the player
        # enters the room. For the other pages to be displayed, we
        # need "layer switching" table entries. This is just a table
        # saying "if the player is on this floor when this page is
        # displayed, switch to this other page".

        layer_switches = set()

        for room in self.scene.rooms:
            if len(room.layers) > 1:
                for layer1, layer2 in itertools.pairwise(room.layers):

                    # The lowest layer is always the default layer for the room
                    # so we need to be able to switch from that to any layer
                    # in case the player enters the room on a higher layer.
                    layer_switches.add((room.layers[0], layer2))

                    # We also need to be able to switch between any two adjacent
                    # layers as the player moves up or down within the room.
                    layer_switches.add((layer1, layer2))
                    layer_switches.add((layer2, layer1))

        layer_switches = list(layer_switches)

        if len(layer_switches) > 51:
            raise Exception(
                "Too many layer switches in scene. Use fewer tall rooms."
            )

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sSwitchEntryCount',
            self.scene.index,
            len(layer_switches)
        )

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sSwitchFromFloor',
            self.scene.index,
            [
                # This is correct despite apparent from/to mismatch.
                # Decomp calls it "from" because we're switching "from" the
                # floor the player is on. We call it "to" because we're
                # switching "to" the map page for that floor.
                7 - to_layer.floor.index
                for from_layer, to_layer in layer_switches
            ]
        )

        def layer_page_index(layer):
            return index_where(self.pages, lambda page: page.layer == layer)
            

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sSwitchFromRoom',
            self.scene.index,
            [
                layer_page_index(from_layer)
                for from_layer, to_layer in layer_switches
            ]
        )

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sSwitchToRoom',
            self.scene.index,
            [
                layer_page_index(to_layer)
                for from_layer, to_layer in layer_switches
            ]
        )


        # Install our finished minimap textures into the OOT assets
        # directory.
        map_i_static_pngs = [
            f'assets/textures/map_i_static/'
            f'_custom_scene{self.scene.index}'
            f'_room{page.layer.room.index}'
            f'_floor{page.layer.floor.index}.i4.png'

            for page in self.pages
        ]

        for page, to_path in zip(self.pages, map_i_static_pngs):
            yield z64c.InstallFile(
                from_path=page.final_image.render_path,
                to_path=to_path
            )

        # ZAPD will create .inc.c files from the PNGs when we build
        # OOT. Include these in the map_i_static file.
        map_i_static_includes = [
            x.replace('.png', '.inc.c')
            for x in map_i_static_pngs
        ]
        yield z64c.ReplaceIncludes(
            path='assets/textures/map_i_static/map_i_static.c',
            names=[
                f'gScene{self.scene.index}'
                f'Room{page.layer.room.index}'
                f'Floor{page.layer.floor.index}MinimapTex'
                for page in self.pages
            ],
            includes=map_i_static_includes,
            first_index=sDgnMinimapTexIndexOffset[self.scene.index]
        )
                


    @cached_property
    @yield_list
    def pages(self) -> list[DungeonMinimapPage]:

        layers = [
            layer
            for room in self.scene.rooms
            for layer in room.layers
        ]

        layers = sorted(
            layers,
            key=lambda layer: (layer.index_in_room, layer.room.index)
        )

        for layer in layers:
            collection = self.scene_map.clipped_layer_geometry(layer)

            bounds = objects_bounds(collection.objects)

            cam_pos = Vec3(bounds.center.x, bounds.center.y, 0)

            cam_scale = 960 * 3 / self.scene.blender_scene.ootBlenderScale

            yield DungeonMinimapPage(
                layer,
                MapCamera(
                    cam_pos,
                    cam_scale,
                    collection,
                    Image(key=('miniraw', self.scene.index, layer.room.index, layer.floor.index))
                ),
                final_image=Image(key=(
                    'minimap',
                    self.scene.index,
                    layer.room.index,
                    layer.floor.index
                ))
            )


    def render_all(self):
        log("Render MINIMAP cameras")
        for page in self.pages:
            self.scene_map.render_map_camera(page.camera)

        log("Process MINIMAP cameras")
        for page in self.pages:

            raw_rgba = PIL.Image.open(page.camera.image.render_path)
            raw_void, raw_surface, _, raw_alpha = raw_rgba.split()

            out_image = PIL.Image.new('P', raw_alpha.size)
            out_image.putpalette(image_utils.ci4_palette)

            w, h = out_image.size

            # Fill, outline, and find bounds
            x0 = None
            y0 = None
            x1 = None
            y1 = None
            has_void = False
            for y in range(h):
                for x in range(w):
                    p = (x, y)
                    in_alpha = raw_alpha.getpixel(p)
                    if in_alpha == 0:

                        if any(
                            image_utils.get(raw_alpha, (x+dx, y+dy), 0) != 0
                            for (dx, dy) in image_utils.dirs8
                        ):
                            out_image.putpixel(p, 15)

                            if x0 is None or p[0] < x0: x0 = p[0]
                            if x1 is None or p[0] > x1: x1 = p[0]
                            if y0 is None or p[1] < y0: y0 = p[1]
                            if y1 is None or p[1] > y1: y1 = p[1]


                    else:
                        if raw_void.getpixel(p) > 128:

                            if any(
                                image_utils.get(raw_surface, (x+dx, y+dy), 0) >= 128
                                for (dx, dy) in image_utils.dirs8
                            ):
                                out_image.putpixel(p, 15)
                            else:
                                out_image.putpixel(p, 0)

                            has_void = True

                        else:
                            out_image.putpixel(p, 4)


            if x0 is None:
                # Empty image
                pass
                
            else:
                bounds = Rect.bounding_points(
                    Vec2(x0, y0),
                    Vec2(x1, y1)
                )

                bounds = bounds.expand(5)

                bounds.size.x -= 1
                bounds.size.y -= 1

                # Draw border
                draw = PIL.ImageDraw.Draw(out_image)
                draw.rectangle(
                    ((bounds.min.x, bounds.min.y),
                     (bounds.max.x, bounds.max.y)),
                    outline=15
                )

                # Blur
                halo = PIL.Image.new('L', out_image.size)
                for y in range(h):
                    for x in range(w):

                        pix = max(raw_alpha.getpixel((x, y)),
                                  out_image.getpixel((x, y)))

                        if pix != 0 or any(
                            image_utils.get(raw_alpha, (x+dx, y+dy), 0)
                            for (dx, dy) in image_utils.dirs4
                        ):
                            halo.putpixel((x, y), 0xb0)

                draw = PIL.ImageDraw.Draw(halo)
                draw.rectangle(
                    ((bounds.min.x, bounds.min.y),
                     (bounds.max.x, bounds.max.y)),
                    outline=0x10
                )
                halo = halo.filter(PIL.ImageFilter.GaussianBlur(1))

                # Composite out_image onto its halo
                for y in range(h):
                    for x in range(w):
                        p = out_image.getpixel((x, y))
                        mask = raw_alpha.getpixel((x, y))
                        if p != 0 or mask != 0:
                            halo.putpixel((x, y), p * 16)

                out_image = halo

                # Shift to lower-right
                shift_x = w - 2 - bounds.max.x
                shift_y = h - 2 - bounds.max.y

                page.shift = mathutils.Vector((shift_x, shift_y))

                out_image = out_image.transform(
                    (w, h),
                    PIL.Image.AFFINE,
                    (1, 0, -shift_x,
                     0, 1, -shift_y),
                    fillcolor=0
                )

            # ZAPD doesn't like grayscale PNGs
            out_image = out_image.convert('RGB')
            out_image.save(page.final_image.render_path)


def get_world_to_compass_mark_transform(cam_pos, cam_scale_x, shift):
    '''

    OOT draws compass marks (red and yellow arrows) in what we'll call
    "compass mark space", which maps to the screen as follows:

         -1600,-1200
         +---------------------+
         |                     |
         |                     |
         |             +-----+ |
         |             |     | |
         |             +-----+ |
         +---------------------+1600,1200

    We want the compass marks to end up inside the minimap at the lower
    right.

    The minimap is drawn to the screen, in normal 320x240 screen space,
    at 204,140 and is 96x85.

        Basic screen coords
        0,0
        +---------------------+
        |                     |
        |          204,140    |
        |             +-----+ |
        |             |     | |
        |             +-----+.|..........300,225
        +---------------------+320,240

    We need to supply the transformation from world space to compass
    mark space, so OOT knows where to draw the compass marks.

    We do this by projecting from world space to minimap texture space,
    then to 320x240 screen space, then finally to compass mark space.

    cam_pos-cam_scale/2
    +---------------------+
    |                     |
    |                     |
    |         +cam_pos    |
    |                     |
    |                     |
    +---------------------+cam_pos+cam_scale/2

    Basic screen coords
    0,0
    +---------------------+
    |                     |
    |          204,140    |
    |             +-----+ |
    |             |     | |
    |             +-----+.|..........300,225
    +---------------------+320,240

    CompassMark
    -1600,-1200
    +---------------------+
    |                     |
    |                     |
    |             +-----+ |
    |             |     | |
    |             +-----+.|
    +---------------------+1600,1200


    We want map_mark_offset_x
    '''

    world_to_texture = get_world_to_96x85_minimap_transform(
        cam_pos,
        cam_scale_x,
        shift
    )

    texture_to_screen = mathutils.Matrix([
        [ 1,  0,  204],
        [ 0,  1,  140],
        [ 0,  0,    1],
    ])

    screen_to_compass_mark = map_rect(
        Rect(Vec2(0, 0), Vec2(320, 240)),
        Rect(Vec2(-1600, 1200), Vec2(3200, -2400))
    )

    world_to_compass_mark = (
        screen_to_compass_mark @
        texture_to_screen @
        world_to_texture
    )

    return world_to_compass_mark


def get_world_to_96x85_minimap_transform(cam_pos, cam_scale_x, shift):
    cam_scale_y = cam_scale_x * 85/96
    cam_scale = Vec2(cam_scale_x, cam_scale_y)

    cam_pos = Vec2(cam_pos[0], cam_pos[1])

    # Convert cam scale & pos from Blender to OOT units
    cam_scale = cam_scale * 10
    cam_pos = cam_pos * 10
    cam_pos.y *= -1

    return map_rect(
        Rect.centered(cam_pos, cam_scale),
        Rect(Vec2(0, 0), Vec2(96, 85)) + shift
    )


