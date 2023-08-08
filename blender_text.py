'''
OOT Scene Tool
By Robin Allen (https://foon.uk)

Load this up in the Blender text editor and Alt+P it.
'''

import bpy, os, sys
this_file_path = bpy.context.space_data.text.filepath
oot_scene_tool_dir = os.path.dirname(this_file_path)
oot_scene_tool_parent = os.path.dirname(oot_scene_tool_dir)
sys.path.append(oot_scene_tool_parent)

import oot_scene_tool
from oot_scene_tool import blender
