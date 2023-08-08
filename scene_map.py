import os

from .utils import *

from . import z64c, app, materials

class SceneMap:
    '''
    Z64 minimap and pause-map data for a scene.

    Intended usage:
       1. Construct SceneMap(scene)
       2. Ask for C code patches with scene.c_diffs

    Features:

    -- PAUSE MAP (DUNGEON) --
        - Dungeon name texture (item_name_nes_static)

    - gPauseMapMarkDataTable (z_lmap_mark_data.c)
        - Chest markers
        - Skull markers

    - sFloorTexIndexOffset
        {0, 0, ..., 2, 4, 6, 8}

    - Floor of the boss icon
        sBossFloor

    - Pause map palette index assignment
        sRoomPalette
        sMaxPaletteCount
        sPaletteRoom

    - Floor IDs
        sFloorID
        High to low, F_1F etc, front-padded with 0.

    - Y coord of big skull icon on map screen
        sSkullFloorIconY
        Redundant with sBossFloor; always 51 - 14 * sBossFloor[i]





    -- MINIMAP (DUNGEON) --
        - Room compass offset
        - sRoomCompassOffsetX
        - sRoomCompassOffsetY

    - Number of minimaps (1 or more per room)
        sDgnMinimapCount

    - Index range of minimap textures from map_i_static
        sDgnMinimapTexIndexOffset

    - Layer switching table
        "Room" here refers to minimaps, not rooms.
        sSwitchEntryCount
        sSwitchFromRoom
        sSwitchFromFloor
        sSwitchToRoom




    -- MINIMAP (OVERWORLD) --
        - sOwMinimapTexSize
        - sOwMinimapTexOffset
        - sOwMinimapPosX/Y
        - sOwCompassInfo
        - sOwMinimapWidth/Height
        - sOwEntranceIconPosX/Y
        - sOwEntranceFlag


    So we're installing stuff into the OOT folder
    Changes are:
    - Diffs to C files
    - Texture files to install

    So, to make a map from a scene, we can construct
    a Scene object, inside or outside of Blender.

    What images do we need?

    - Map name texture

    - map_i_static
      One per minimap
      Each room has 1-n minimaps
      Each minimap has a cam pos
      Each scene has a minimap scale

      So, Blender should fill out
      room_floor.minimap with image path

      RoomFloor -> (Render, CamPos)
      

    - map_48x85_static
      - Two per floor
      - Scene has dungeon_map_cam_pos & scale

      So, Blender should fill out
      room_floor.dungeon_map with image path

      Floor -> (Render, CamPos, CamSize)
      

    - map_grand_static
      - One per scene


    We shouldn't mandate any particular minimap
    style. People shouldn't HAVE to use blender
    renders or our postprocessor. 
    SceneMap should be happy to install ANY
    image.

    We should provide a way of creating the
    required data from the Blender scene:
    - renders -> map images
    - cam data


    Also want install without Blender
    - Use specified renders and cam positions

    SceneMap will happily install given:
       - For dungeons:
            Minimap CamScale
            RoomFloor -> (CamPos, MinimapImage 96x85)

            PauseMap CamScale
            Floor -> DungeonMapImage

         For OW:
            Minimap CamScale, CamPos, Image 64x59


    In Blender we want to create this map data
    SceneMap wants to consume it




    How about

    Scene

    MapData
      install this into C

    MapRenders


    '''
    def __init__(self, scene):
        from .dungeon_minimap import DungeonMinimap
        from .dungeon_pause_map import DungeonPauseMap

        self.scene = scene

        self.minimap = DungeonMinimap(self)
        self.pause_map = DungeonPauseMap(self)

    @property
    @yield_list
    def diffs(self):

        z_map_data = 'src/code/z_map_data.c'

        # Floor coords
        # High to low, front-padded with 9999.0f.
        # Last one is ignored.
        yield z64c.CArrayItem(
            z_map_data,
            'sFloorCoordY',
            self.scene.index,
            pad_front(
                list(reversed([floor.z0 * 10 for floor in self.scene.floors])),
                8,
                9999.0
            )
        )

        yield from self.minimap.diffs
        yield from self.pause_map.diffs

    @functools.lru_cache
    def clipped_layer_geometry(self, layer):
        collection = self.scene.helper_collection(
            str(layer),
            parent=self.scene.helper_collection(
                "Clipped Layer Geometry"
            )
        )
        for obj in layer.room.geometry_objects:
            clipped_obj = duplicate_object(obj, collection)
            clipped_obj.name = f'{obj.name} {layer}'

            # This object isn't for Fast64 export.
            # TODO: Maybe cleaner to just unparent it from the F64 room.
            clipped_obj.ignore_render = True
            clipped_obj.ignore_collision = True

            # TODO: Create this material
            mat_room = materials.get_surface()

            clipped_obj.data.materials.clear()
            clipped_obj.data.materials.append(mat_room)

            # TODO: Create this node group
            mod = clipped_obj.modifiers.new('mod', 'NODES')
            mod.node_group = bpy.data.node_groups['FlipNormals']

            clip_object(clipped_obj, layer.floor.volume_object)

            # TODO: Create this node group
            mod = clipped_obj.modifiers.new('mod', 'NODES')
            mod.node_group = bpy.data.node_groups['FlipNormals']
        return collection
        

    @property
    def minimap_camera_object(self):
        cam = bpy.data.objects.get("Map Camera")
        if cam:
            return cam
        
        cam = bpy.data.objects.new(
            name="Map Camera",
            object_data=(
                bpy.data.cameras.get('Map Camera') or
                bpy.data.cameras.new("Map Camera")
            )
        )
        self.scene.helpers.objects.link(cam)
        return cam

    def render_map_camera(self, map_camera):
        cam = self.minimap_camera_object
        cam.location.x = map_camera.camera_pos.x
        cam.location.y = map_camera.camera_pos.y
        cam.location.z = 100

        for obj in bpy.data.objects:
            obj.hide_render = obj.name not in map_camera.collection.all_objects

        map_camera.collection.hide_render = False

        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = map_camera.camera_scale
        
        bpy.context.scene.render.resolution_x = 96
        bpy.context.scene.render.resolution_y = 85
        bpy.context.scene.render.engine = 'CYCLES'

        # Disable antialiasing
        bpy.context.scene.cycles.samples = 1
        bpy.context.scene.cycles.use_adaptive_sampling = False
        bpy.context.scene.cycles.use_denoising = False

        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = map_camera.image.render_path
        log(f"Render {map_camera.image.render_path}")
        bpy.ops.render.render(
            write_still=True
        )

    def render_all(self):
        self.minimap.render_all()
        self.pause_map.render_all()

    def install(self):
        pass

    @yield_list
    def chests(self, actors):
        for obj in actors:
            if obj.ootActorProperty.actorID == 'ACTOR_EN_BOX':
                param = int(obj.ootActorProperty.actorParam, 0)
                chest_flag = param & 0x1f
                blender_pos = obj.matrix_world.translation
                oot_pos = self.scene.blender_to_oot_pos(blender_pos)
                yield chest_flag, oot_pos
    

@dataclass
class MapCamera:
    camera_pos: object
    camera_scale: float
    collection: object
    image: object
