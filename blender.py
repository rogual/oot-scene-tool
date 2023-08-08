
from importlib import reload

import contextlib
import subprocess
import sys
import os
import re

import bpy

oot_scene_tool_dir = os.path.dirname(__file__)
make = '/usr/local/bin/gmake'


# TOOLS PATH
# ----------
# I add this to my path in my .bash_profile, which Blender
# can't really be expected to read. Instead of fixing
# my system, I'll just YOLO this here.
path = '/opt/cross/bin/'
if path not in os.environ['PATH'].split(':'):
    os.environ['PATH'] += ':' + path
path = '/usr/local/bin/'
if path not in os.environ['PATH'].split(':'):
    os.environ['PATH'] += ':' + path


# DEPENDENCIES
# ------------
pil_installed = None
try:
    import PIL
    pil_installed = True
except ImportError:
    pil_installed = False

if not pil_installed:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pillow'])


# LOAD OR RELOAD THIS TOOL
# ------------------------
# Why does anyone think Python is good
import oot_scene_tool
from oot_scene_tool import scene, scene_map, app, utils, z64c, text, scene_split, lighting, blender


def reload_this_tool():
    # TODO This doesn't even work because you can't reload blender.py
    # itself because it throws some shitty error. Fuck sake. How is
    # anyone supposed to code for Blender. I mean, what is the intended
    # workflow? Just edit, click-click, gui, Alt-R, Confirm, reload,
    # for every change?
    utils.log("-----Why is this even complicated")
    to_reload = []
    for name, module in sys.modules.items():
        file = getattr(module, '__file__', None)
        if file and file.startswith(oot_scene_tool_dir):

            # Blender does some cute shit where a module has a path
            # inside a Blend file even though a Blend file is not
            # a fucking directory, so it just breaks everything
            if '.blend' not in file:
                to_reload.append(module)

    for module in to_reload:
        try:
            utils.log(module.__file__)
            reload(module)
        except ModuleNotFoundError:
            # Just fuck off
            utils.log("FUCK SAKE")
            # Programming doesn't need to be like this
            pass

reload_this_tool()


# GO GO GO
# --------
log = utils.log


@contextlib.contextmanager
def with_scene():
    app.scene = scene.Scene(
        bpy.context.scene
    )
    scene_split.split(app.scene)
    yield
    app.scene = None


operators = []

@utils.cache_as_property('_oot_scene_tool_operator')
def define_operator(fn):
    """
    This takes a normal function, like a small-brain novice programmer
    or child/baby might use, and turns it into a big-brain OOP Java
    webscale factory-pattern agile reusable modular HD-ready OPERATOR
    CLASS, like a prestigious adult serious modern programmer would
    use. Utilize. They'd say utilize.
    """

    # Name our class three times because serious programmers are paid
    # by the hour.
    snake = fn.__name__
    title = re.sub('(^|_)([A-Za-z0-9])', lambda m: m.group(1).replace('_', ' ') + m.group(2).title(), snake)

    for acronym in ['OOT', 'PIL', 'AO']:
        title = title.replace(acronym.title(), acronym)

    camel = title.replace(' ', '')

    class Op(bpy.types.Operator):
        bl_idname = f'foon.{snake}'
        bl_label = title
        def execute(self, context):
            with with_scene():
                fn() # <-- The actual thing we wanted to do
            return {'FINISHED'}   

    Op.__name__ = camel
    bpy.utils.register_class(Op)
    operators.append(Op)

    return Op


@define_operator
def install_pil():
    global pil_installed
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pillow'])
    pil_installed = True


@define_operator
def reload_tool():
    # Don't just reload now; we need to wait for Blender's stack to clear
    # or it will just unceremoniously crash.
    def defer():
        reload_this_tool()
    bpy.app.timers.register(defer, first_interval=0)


@define_operator
def bake_ao():
    name = 'AO'
    app.scene.blender_scene.render.engine = 'CYCLES'
    app.scene.blender_scene.cycles.bake_type = 'AO'
    app.scene.blender_scene.render.bake.target = 'VERTEX_COLORS'

    mesh = bpy.context.active_object.data
    ao = mesh.color_attributes.get(name)
    if not ao:
        ao = mesh.color_attributes.new(name, 'FLOAT_COLOR', 'CORNER')

    mesh.color_attributes.active = ao

    bpy.ops.object.bake('AO')


@define_operator
def merge_vertex_colors():
    lighting.merge_vertex_colors(app.scene)


@define_operator
def split_rooms():
    scene_split.split(app.scene)


@define_operator
def move_actors_to_rooms():
    scene_split.move_actors_to_their_rooms(app.scene)
    

@define_operator
def render_maps():
    map_ = scene_map.SceneMap(app.scene)
    map_.render_all()
    z64c.install_diffs(app.scene.oot_dir, map_.diffs)


@define_operator
def export_scene():
    bpy.ops.object.oot_export_level()


@define_operator
def compile_oot():
    subprocess.check_call(
        [make, '-j', 'NON_MATCHING=1'],
        cwd=app.scene.oot_dir,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


@define_operator
def init_fast64():
    app.scene.blender_scene.gameEditorMode = 'OOT'


bpy.types.Scene.rgaSceneName = bpy.props.StringProperty(
    name="Scene Display Name"
)


import random
fuck_you = random.randint(0, 1000)

@bpy.utils.register_class
class OOT_SCENE_TOOL_PT_panel(bpy.types.Panel):
    """
    Sidebar panel. Blender has Opinions on what you call stuff
    in your own code, so the class name has to be full of
    uppercase and inscrutable abbreviations, just like the
    Blender code itself. If I had my way it'd be "Panel".
    """
    bl_label = "OOT Scene Tool"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OOT"

    def draw(self, context):
        col = self.layout.column(align=True)
        import random
        col.label(text=str(fuck_you))
        for operator in operators:
            if operator.bl_idname == 'foon.install_pil' and pil_installed:
                continue
            col.operator(operator.bl_idname)

        col.prop(context.scene, "rgaSceneName")
        col.prop(context.scene, "rgaProjectDir")

