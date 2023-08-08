from dataclasses import dataclass

import bpy
import mathutils

import PIL.Image

from .scene_map import MapCamera, Image
from .utils import *

from . import image_utils
from . import z64c
from . import app
from . import text


class DungeonPauseMapLayer:
    def __init__(self, layer, camera):
        self.layer = layer
        self.camera = camera


@dataclass
class DungeonPauseMapPage:
    floor: object
    image: object
    halves: object
    layers: object
    c_halves: object
    

class DungeonPauseMap:
    '''
    This is the map you see on the Map Subscreen.

    It has several pages, one per dungeon floor.

    Each page is made of one or more layers, one per room. The final image
    textures are composited from all the layers on that floor.

    '''
    def __init__(self, scene_map):
        self.scene_map = scene_map
        self.scene = scene_map.scene
        self.room_palettes = {}

        self.cam_pos = self.scene.center

        #    /-Margin           /-Margin
        #    |                  |
        #  |   | Scene Bounds |   |
        #  |   |Projected Here|   |
        #  |                      |
        #  `----------96x85-------/

        # TODO: Not sure if this is actually right. I can't maths it right now.
        # Just trying to ensure a margin. Maps look weird if they go right to
        # the edge of the texture.
        margin_pixels = 8
        scale_up = (96 / (96 - 2 * margin_pixels))
        
        cam_scale_x = self.scene.bounds.x.size
        cam_scale_y = self.scene.bounds.y.size * 96 / 85
        self.cam_scale = max(cam_scale_x, cam_scale_y) * scale_up

        # Apply a minimum scale. In OOT, the smallest dungeon is the Deku Tree
        # which seems to use a pause-map scale of about 4,362 OOT units, so
        # let's use that.
        #
        # (You can figure this out by checking the distance between treasure
        # chests in a scene's actor list vs. the distance between the corresponding
        # map marks.)
        #
        # Note: OOT pause maps are not always to scale; they seem to have been
        # manually altered after rendering, so these figures can't be exact.
        # self.cam_scale = max(self.cam_scale, 436)
        # self.cam_scale = max(self.cam_scale, 300)

        log("Pause map cam scale is", self.cam_scale)

        self.world_to_map_transform = get_world_to_96x85_dungeon_map_transform(
            self.cam_pos,
            self.cam_scale
        )

        # 0..7, 7 being the lowest
        self.boss_floor = 7

        # If 0, the lowest floor will be 1F.
        # If 1, the lowest floor will be B1, and so on.
        self.num_basement_floors = 0

        self.title_image = Image(('pause_title', self.scene.index))


    @cached_property
    @yield_list
    def pages(self):

        cam_pos = self.cam_pos
        cam_scale = self.cam_scale

        for floor in self.scene.floors:

            halves = [
                Image(key=('pause_left', self.scene.index, floor.index)),
                Image(key=('pause_right', self.scene.index, floor.index)),
            ]

            c_halves = [
                half.render_path.replace('.png', '.inc.c')
                for half in halves
            ]

            yield DungeonPauseMapPage(
                floor=floor,
                image=Image(key=('pause_floor', self.scene.index, floor.index)),
                halves=halves,
                c_halves=c_halves,
                layers=[
                    DungeonPauseMapLayer(
                        layer,
                        MapCamera(
                            cam_pos,
                            cam_scale,
                            collection=self.scene_map.clipped_layer_geometry(layer),
                            image=Image(key=('pause_layer', self.scene.index, floor.index, layer.room.index))
                        )
                    )
                    for layer in floor.layers
                ]
            )


    @cached_property
    def diffs(self):

        # Install our finished pause map textures into the OOT
        # assets directory.
        map_48x85_static_pngs = [
            f'assets/textures/map_48x85_static/'
            f'_custom_scene{self.scene.index}'
            f'_floor{page.floor.index}'
            f'_{side}.ci4.png'

            for page in self.pages
            for side in ['left', 'right']
        ]

        from_image_halves = [
            page.halves[i]
            for page in self.pages
            for i in [0, 1]
        ]

        # We don't really have to install these PNGs into the decomp dir, since
        # we're not letting ZAPD convert them, but let's do it anyway.
        for image_half, png in zip(from_image_halves, map_48x85_static_pngs):
            yield z64c.InstallFile(
                from_path=image_half.render_path,
                to_path=png
            )

        # Instead of letting ZAPD convert our PNGs to .inc.c files, we do
        # it ourselves; see comment in dungeon_map_image_to_c.
        map_48x85_static_includes = [
            x.replace('.png', '.inc.c')
            for x in map_48x85_static_pngs
        ]

        from_inc_c = [
            page.c_halves[i]
            for page in self.pages
            for i in [0, 1]
        ]

        for inc_c, dest in zip(from_inc_c, map_48x85_static_includes):
            yield z64c.InstallFile(
                from_path=inc_c,
                to_path='build/' + dest
            )

        # Update the main asset file to include our generated .inc.c files.
        yield z64c.ReplaceIncludes(
            path='assets/textures/map_48x85_static/map_48x85_static.c',
            names=[
                f'gScene{self.scene.index}'
                f'PauseScreenMapFloor{page.floor.index}{side}Tex'
                for page in self.pages
                for side in ['Left', 'Right']
            ],
            includes=map_48x85_static_includes,
            first_index=0
        )

        # Install the title image
        title_path = f'assets/textures/icon_item_nes_static/pause_scene_{self.scene.index}_title_eng.ia8.png'
        yield z64c.InstallFile(
            from_path=self.title_image.render_path,
            to_path=title_path
        )

        # Update the title asset file to reference our new title image.
        # Keep the decomp scene names; saves us having to update the array in z_kaleido_map_PAL.c
        decomp_scene_names = 'Deku Dodongo Jabu Forest Fire Water Spirit Shadow BotW IceCavern'.split()
        yield z64c.ReplaceIncludes(
            path='assets/textures/icon_item_nes_static/icon_item_nes_static.c',
            names=[
                #f'gPauseScene{self.scene.index}TitleENGTex'
                f'gPause{decomp_scene_names[self.scene.index]}TitleENGTex'
            ],
            includes=[
                title_path.replace('.png', '.inc.c')
            ],
            first_index=self.scene.index
        )

        # There's no explicit "number of floors" array; figure it out
        # from the texture index offsets
        sFloorTexIndexOffset = z64c.read_array(
            app.scene.oot_dir,
            'src/code/z_map_data.c',
            'sFloorTexIndexOffset'
        )
        num_floors = [
            9 - xs.count(0)
            for xs in sFloorTexIndexOffset
        ]

        # Write our offsets.
        # This is how OOT knows which range of textures in the asset
        # file corresponds to our scene. We need to rewrite the whole
        # base array because we might have moved other scenes' data
        # around.
        old_num_floors = num_floors[self.scene.index]
        old_tex_index_offset = 2 * sum(num_floors[:self.scene.index])

        num_floors[self.scene.index] = len(self.pages)
        yield z64c.CArray(
            'src/code/z_map_data.c',
            'sDgnTexIndexBase',
            [
                2 * sum(num_floors[:i])
                for i in range(10)
            ]
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sFloorTexIndexOffset',
            self.scene.index,
            pad_front([2 * i for i in range(len(self.pages))], 8, 0)
        )

        # Skull icon indicating boss floor
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sBossFloor',
            self.scene.index,
            self.boss_floor
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sSkullFloorIconY',
            self.scene.index,
            51 - 14 * self.boss_floor
        )

        # Floor IDs
        def floor_id(height):
            if height >= 0:
                return f'F_{height + 1}F'
            return f'F_B{-height}'

        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sFloorID',
            self.scene.index,
            pad_front(
                [
                    floor_id(i - self.num_basement_floors)
                    for i in reversed(range(len(self.pages)))
                ],
                8,
                0
            ),
            format_hint='floor_ids'
        )

        # Just the number of rooms on each floor.
        max_palette_count = max(
            len(floor.rooms)
            for floor in self.scene.floors
        )
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sMaxPaletteCount',
            self.scene.index,
            max_palette_count
        )

        # Room palette indices.
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sRoomPalette',
            self.scene.index,
            [
                self.room_palettes[room]
                for room in self.scene.rooms
            ]
        )

        # Just a list of used palette indices on each floor.
        yield z64c.CArrayItem(
            'src/code/z_map_data.c',
            'sPaletteRoom',
            self.scene.index,
            [
                pad_back(
                    list(sorted(
                        self.room_palettes[room]
                        for room in floor.rooms
                    )),
                    max_palette_count,
                    255
                )
                for floor in self.scene.floors
            ]
        )

        # Map Marks

        map_marks = []

        for page in reversed(self.pages):
            floor_marks = []
            map_marks.append(floor_marks)

            chest_marks = []
            for chest_flag, oot_pos in self.scene_map.chests(page.floor.actors):
                mark_pos = self.world_to_map_transform @ mathutils.Vector((
                    oot_pos.x,
                    oot_pos.z,
                    1
                ))

                # The dungeon map texture is drawn with Y coords from 28 to -57
                # and X coords from -36 to 60.
                # (Look at mapPageVtx[60:68], set up in KaleidoScope_InitVertices)
                #
                # The map marks are then drawn on top with the translation matrix set
                # to (-36, 21). We need to add the extra 7 (28 - 21) to get the Y coords
                # to line up.
                chest_marks.append([
                    chest_flag,
                    int(round(mark_pos.x)),
                    int(round(mark_pos.y)) * -1 + 7,
                ])

            if chest_marks:
                floor_marks.append([
                    'PAUSE_MAP_MARK_CHEST',
                    23, # Always 23. Seems unused.
                    'sMarkChestVtx',
                    4,
                    len(chest_marks),
                    chest_marks
                ])

            floor_marks.append(['PAUSE_MAP_MARK_NONE', 0, 'NULL', 0, 0, [0]])

        yield z64c.CArrayRange(
            'src/overlays/misc/ovl_kaleido_scope/z_lmap_mark_data.c',
            'gPauseMapMarkDataTable',
            old_tex_index_offset // 2,
            old_num_floors,
            map_marks
        )


    @cached_property
    def floor_images(self):
        return [
            Image(('pause_map_floor', self.scene.index, floor.index))
            for floor in self.scene.floors
        ]


    def render_all(self):
        log("Render PAUSE MAP title")
        text.render_text(self.scene.display_name, (96, 16), self.title_image.render_path)
        
        log("Render PAUSE MAP cameras")

        # Assign palette indices to rooms such that no two rooms on a
        # given floor have the same palette indices. "palette" here
        # is short for "palette index".
        all_palettes = set(range(1, 14))
        room_palettes = self.room_palettes = {}

        ok = True
        for floor in self.scene.floors:
            if floor.rooms == []:
                print(f"Error: {floor} has no rooms")
                ok = False
        if not ok:
            raise Exception()

        for floor in self.scene.floors:
            print(f"Floor: {floor}")
            for room in floor.rooms:
                print(f" Room: {room}")

            floor_used_palettes = set(
                x for x in [
                    room_palettes.get(room)
                    for room in floor.rooms
                ]
                if x is not None
            )

            floor_available_palettes = all_palettes - floor_used_palettes

            for room in floor.rooms:
                if room not in room_palettes:

                    if not floor_available_palettes:
                        raise Exception(
                            f"There are too many rooms on "
                            f"{floor}. Max 13."
                        )

                    room_palette = room_palettes[room] = \
                        min(floor_available_palettes)

                    floor_available_palettes.remove(room_palette)

        # Check we did it okay
        if not all(room in room_palettes for room in self.scene.rooms):
            print(f"Palettes assigned to rooms:")
            for room, palette in room_palettes.items():
                print(f"    {room}: palette {palette}")
            print(f"Errors:")
            for room in self.scene.rooms:
                if room not in room_palettes:
                    print(f"        {room} has not been assigned a palette.")
            raise Exception("Palette fail")


        for floor in self.scene.floors:
            assert len(floor.rooms) == len(set(room_palettes[x] for x in floor.rooms))

        sz = (w, h) = (96, 85)

        # Render all the room maps and combine them by floor

        for page in self.pages:

            for layer in page.layers:
                self.scene_map.render_map_camera(layer.camera)

            floor_map = PIL.Image.new('P', sz)
            floor_map.putpalette(image_utils.ci4_palette)

            for layer in page.layers:
                room = layer.layer.room
                room_palette_index = room_palettes[room]

                room_image = PIL.Image.open(layer.camera.image.render_path)
                room_alpha = room_image.split()[-1]

                for y in range(h):
                    for x in range(w):
                        if room_alpha.getpixel((x, y)):
                            floor_map.putpixel((x, y), room_palette_index)


            image_utils.fast_outline(floor_map, 15)

            floor_map.save(page.image.render_path)

            half = floor_map.crop((0, 0, 48, 85))
            half.save(page.halves[0].render_path)

            half = floor_map.crop((48, 0, 96, 85))
            half.save(page.halves[1].render_path)

            for i in [0, 1]:
                dungeon_map_image_to_c(page.halves[i].render_path, page.c_halves[i])



def dungeon_map_image_to_c(image_path, c_path):
    # I haven't had any luck getting ZAPD to convert dungeon
    # map PNGs into the right format.  Our map processor
    # writes out ci4 PNGs, and OOT wants raw ci4 data.  But if
    # you feed ZAPD a ci4 PNG, it just seems to make a mess of
    # it?  ZAPD extracts vanilla ci4 textures as ci8 PNGs, so
    # maybe those would work... PIL documents a "bits" flag to save() that lets you
    # specify ci8, but it doesn't work. And converting PNGs
    # with ImageMagick with "png8:filename" doesn't preserve
    # colour indices.
    #
    # Let's just write our own god damn file.
    image = PIL.Image.open(image_path)
    
    with open(c_path, 'wt') as f:
        i = 0
        addr = 0
        for y in range(85):
            for x in range(48):
                if i % 64 == 0:
                    f.write('    ')
                if i % 16 == 0:
                    f.write('0x')
                f.write('0123456789ABCDEF'[image.getpixel((x, y))])
                i += 1
                if i % 16 == 0:
                    f.write(', ')

                if i % 64 == 0:
                    f.write(' // 0x%06X\n' % addr)
                    addr += 32

    
def get_world_to_96x85_dungeon_map_transform(cam_pos, cam_scale_x):
    cam_scale_y = cam_scale_x * 85/96
    cam_scale = Vec2(cam_scale_x, cam_scale_y)

    cam_pos = Vec2(cam_pos[0], cam_pos[1])

    # Convert cam scale & pos from Blender to OOT units
    cam_scale = cam_scale * 10
    cam_pos = cam_pos * 10
    cam_pos.y *= -1

    return map_rect(
        Rect.centered(cam_pos, cam_scale),
        Rect(Vec2(0, 0), Vec2(96, 85))
    )
