import bpy

def get_void():
    name = 'DMVoid'
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
    return mat


def get_surface():
    name = 'DMVoid'
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
    return mat
