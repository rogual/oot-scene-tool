from .utils import *

def get_world_to_minimap_transform(minimap_size, cam_pos, cam_scale_x, shift):
    w, h = minimap_size
    cam_scale_y = cam_scale_x * h/w
    cam_scale = Vec2(cam_scale_x, cam_scale_y)

    cam_pos = Vec2(cam_pos[0], cam_pos[1])

    # Convert cam scale & pos from Blender to OOT units
    cam_scale = cam_scale * 10
    cam_pos = cam_pos * 10
    cam_pos.y *= -1

    return map_rect(
        Rect.centered(cam_pos, cam_scale),
        Rect(Vec2(0, 0), Vec2(w, h)) + shift
    )


def get_world_to_compass_mark_transform(
    minimap_pos,
    minimap_size,
    cam_pos,
    cam_scale_x,
    shift
):
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
    at minimap_pos (204,140 for dungeons, overworld maps vary) and is
    minimap_size (96x85 for dungeons, overworld maps vary).

        Basic screen coords
        0,0
        +---------------------+
        |                     |
        |        minimap_pos  |
        |             +-----+ |
        |             |     | |
        |             +-----+.|..........minimap_pos+minimap_size
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
    |      minimap_pos    |
    |             +-----+ |
    |             |     | |
    |             +-----+.|..........minimap_pos+minimap_size
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

    '''

    x, y = minimap_pos

    world_to_texture = get_world_to_minimap_transform(
        minimap_size,
        cam_pos,
        cam_scale_x,
        shift
    )

    texture_to_screen = mathutils.Matrix([
        [ 1,  0,  x],
        [ 0,  1,  y],
        [ 0,  0,  1],
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

