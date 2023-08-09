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
        from .overworld_minimap import OverworldMinimap

        self.scene = scene

        if self.dungeon_index is not None:
            self.minimap = DungeonMinimap(self)
            self.pause_map = DungeonPauseMap(self)

        elif self.overworld_index is not None:
            self.minimap = OverworldMinimap(self)
            self.pause_map = None
            

    @property
    def dungeon_index(self):
        try:
            return [
                'SCENE_DEKU_TREE',
                'SCENE_DODONGOS_CAVERN',
                'SCENE_JABU_JABU',
                'SCENE_FOREST_TEMPLE',
                'SCENE_FIRE_TEMPLE',
                'SCENE_WATER_TEMPLE',
                'SCENE_SPIRIT_TEMPLE',
                'SCENE_SHADOW_TEMPLE',
                'SCENE_BOTTOM_OF_THE_WELL',
                'SCENE_ICE_CAVERN',
            ].index(self.scene.enum_name)
        except ValueError:
            return None

    @property
    def overworld_index(self):
        try:
            return [
                'SCENE_HYRULE_FIELD',
                'SCENE_KAKARIKO_VILLAGE',
                'SCENE_GRAVEYARD',
                'SCENE_ZORAS_RIVER',
                'SCENE_KOKIRI_FOREST',
                'SCENE_SACRED_FOREST_MEADOW',
                'SCENE_LAKE_HYLIA',
                'SCENE_ZORAS_DOMAIN',
                'SCENE_ZORAS_FOUNTAIN',
                'SCENE_GERUDO_VALLEY',
                'SCENE_LOST_WOODS',
                'SCENE_DESERT_COLOSSUS',
                'SCENE_GERUDOS_FORTRESS',
                'SCENE_HAUNTED_WASTELAND',
                'SCENE_HYRULE_CASTLE',
                'SCENE_DEATH_MOUNTAIN_TRAIL',
                'SCENE_DEATH_MOUNTAIN_CRATER',
                'SCENE_GORON_CITY',
                'SCENE_LON_LON_RANCH',
                'SCENE_OUTSIDE_GANONS_CASTLE',
            ].index(self.scene.enum_name)
        except ValueError:
            return None

    @property
    @yield_list
    def diffs(self):

        # Floor coords (dungeons only).
        # High to low, front-padded with 9999.0f.
        # Last one is ignored.
        if self.dungeon_index:
            yield z64c.CArrayItem(
                'src/code/z_map_data.c',
                'sFloorCoordY',
                self.scene.index,
                pad_front(
                    list(reversed([floor.z0 * 10 for floor in self.scene.floors])),
                    8,
                    9999.0
                )
            )

        yield from self.minimap.diffs
        if self.pause_map:
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

        if map_camera.collection:
            for obj in bpy.data.objects:
                obj.hide_render = obj.name not in map_camera.collection.all_objects

            map_camera.collection.hide_render = False

        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = map_camera.camera_scale
        
        bpy.context.scene.render.resolution_x = map_camera.resolution.x
        bpy.context.scene.render.resolution_y = map_camera.resolution.y
        bpy.context.scene.render.engine = 'CYCLES'

        # Transparent background
        bpy.context.scene.render.film_transparent = True

        # Disable antialiasing
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
        if self.pause_map:
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
    resolution: object
    collection: object
    image: object
