import sys
import os
import re
import glob
import pathlib
import textwrap
import functools
import collections

from dataclasses import dataclass, field

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from .text import render_text
from . import z64c

app = QApplication(sys.argv)

global_scale = 3
global_offset = (108, 58)

oot = '/Users/me/Projects/Contrib/oot'

'''
12 map points
Flags in worldMapPoints[]
Positions in mapPageVtx[124 + i * 4], 4 verts each
'''


aco = [
    0x002F, 0xFFCF, 0xFFEF, 0xFFF1, 0xFFF7, 0x0018, 0x002B, 0x000E, 0x0009, 0x0026, 0x0052,
    0x0047, 0xFFB4, 0xFFA9, 0xFF94, 0xFFCA, 0xFFA3, 0xFFBD, 0xFFC8, 0xFFDF, 0xFFF6, 0x0001,
    0x000E, 0x0018, 0x0023, 0x003A, 0x004A, 0x0059, 0x0000, 0xFFC6, 0x0013, 0x001C,
]

bco = [
    0x000F, 0x0028, 0x000B, 0x002D, 0x0034, 0x0025, 0x0024, 0x0039, 0x0036, 0x0021, 0x001F,
    0x002D, 0x0020, 0x002A, 0x0031, 0xFFF6, 0x001F, 0x001B, 0x000F, 0xFFCF, 0x0008, 0x0026,
    0x0007, 0x002F, 0x001E, 0x0001, 0xFFF7, 0x0019, 0x0000, 0x0001, 0xFFE0, 0xFFE6,
]

map_name_static_c = f'assets/textures/map_name_static/map_name_static.c'
kaleido_map_c = f'src/overlays/misc/ovl_kaleido_scope/z_kaleido_map_PAL.c'
kaleido_scope_c = f'src/overlays/misc/ovl_kaleido_scope/z_kaleido_scope_PAL.c'


def load_mask(path, color):
    mask = QImage(path)
    image = QImage(mask.size(), QImage.Format_ARGB32)
    image.fill(color)
    image.setAlphaChannel(mask)
    return QPixmap(image)


class AreaScenes:
    def __init__(self):
        self.scenes_by_area = collections.defaultdict(list)
        # Find world map areas of all overworld scenes
        for path in glob.glob(f'{oot}/assets/scenes/*/*/*_scene.c'):

            scene_name = pathlib.Path(path).stem
            with open(path, 'rt') as f:
                c = f.read()
            m = re.search(r'SCENE_CMD_MISC_SETTINGS\((.*?), (.*?)\)', c)
            if m:
                area = int(m.group(2), 0)
                self.scenes_by_area[area].append(scene_name)

area_scenes = AreaScenes()


@dataclass
class Sprite:
    index: int
    pos: object
    size: object
    kind: str
    texture: object

class Sprites:
    def __init__(self):
        pos_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AEC0')
        pos_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AF78')
        size_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AAEC')
        size_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AB2C')
        n = len(pos_x)

        def sign(x):
            return x if x < 0x8000 else x - 65536

        pos_x = [sign(x) for x in pos_x]
        pos_y = [sign(x) for x in pos_y]

        kinds = (
            ['cloud'] * 16 +
            ['point'] * 12 +
            ['unknown'] * 2 +
            ['place_name'] +
            ['current_position_label']
        )

        self.objects = [
            Sprite(i, *row, None)
            for i, row in enumerate(zip(
                zip(pos_x, pos_y),
                zip(size_x, size_y),
                kinds
            ))
        ]

        self.objects[30].texture = QPixmap(
            f'{oot}/assets/textures/map_name_static/kakariko_village_position_name_eng.ia8.png'
        )

        self.objects[31].texture = load_mask(
            f'{oot}/assets/textures/icon_item_nes_static/pause_current_position_eng.i4.png',
            QColor(0, 0, 0, 255)
        )

    def objects_of_kind(self, kind):
        if isinstance(kind, str):
            kind = (kind,)
        return [x for x in self.objects if x.kind in kind]

sprites = Sprites()


class DataItem(QGraphicsPixmapItem):
    def __init__(self, data, pixmap):
        super().__init__(pixmap)
        self.data = data
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)



class UILabels:
    name = "UI Labels"
    def __init__(self):
        self.objects = sprites.objects_of_kind(('place_name', 'current_position_label'))

ui_labels = UILabels()


@dataclass
class AreaBox:
    index: int
    pos: object
    size: object
    texture_index: int
    

class AreaBoxes:
    def __init__(self):
        pos_x = z64c.read_array(oot, kaleido_map_c, 'areaBoxPosX')
        pos_y = z64c.read_array(oot, kaleido_map_c, 'areaBoxPosY')
        size_x = z64c.read_array(oot, kaleido_map_c, 'areaBoxWidths')
        size_y = z64c.read_array(oot, kaleido_map_c, 'areaBoxHeights')
        tex = z64c.read_array(oot, kaleido_map_c, 'areaBoxTexs')

        positions = list(zip(pos_x, pos_y))
        sizes = list(zip(size_x, size_y))

        texture_indices = [
            int(re.match(r'gWorldMapAreaBox(\d)Tex', x).group(1)) - 1
            for x in tex
        ]

        self.boxes = [
            AreaBox(i, *row)
            for i, row in enumerate(zip(positions, sizes, texture_indices))
        ]

        self.texture_sizes = [None] * 8
        for texture_index, size in zip(texture_indices, sizes):
            self.texture_sizes[texture_index] = size

        assert None not in self.texture_sizes
        assert len(set(zip(texture_indices, sizes))) == len(set(texture_indices))

    def get_box_texture_path(self, index):
        return f'{oot}/assets/textures/icon_item_field_static/world_map_area_box_{index+1}.ia4.png'

    @functools.cache
    def get_box_texture(self, index):
        return QPixmap(self.get_box_texture_path(index))


area_boxes = AreaBoxes()


@dataclass
class Cloud:
    index: int
    pos: object
    size: object
    texture_index: int
    flag: int


class Clouds:
    def __init__(self):
        pos_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AEC0')
        pos_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AF78')
        size_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AAEC')
        size_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AB2C')
        tex = z64c.read_array(oot, kaleido_map_c, 'cloudTexs')
        flag = z64c.read_array(oot, kaleido_map_c, 'cloudFlagNums')
        # If gBitFlags[flag] & save.worldMapAreaData == 0, cloud is drawn

        def sign(x):
            return x if x < 0x8000 else x - 65536

        pos_x = [sign(x) for x in pos_x]
        pos_y = [sign(x) for x in pos_y]

        texture_indices = [
            int(re.match(r'gWorldMapCloud(\d+)Tex', x).group(1)) - 1
            for x in tex
        ]

        positions = list(zip(pos_x, pos_y))
        sizes = list(zip(size_x, size_y))
        self.clouds = [
            Cloud(i, *row)
            for i, row in enumerate(zip(positions, sizes, texture_indices, flag))
        ]

        self.texture_sizes = [None] * 16
        for texture_index, size in zip(texture_indices, sizes):
            self.texture_sizes[texture_index] = size

    def get_cloud_texture_path(self, index):
        return f'{oot}/assets/textures/icon_item_field_static/world_map_cloud_{index+1}.i4.png'

    @functools.cache
    def get_cloud_texture(self, index):
        mask = QImage(self.get_cloud_texture_path(index))

        image = QImage(mask.size(), QImage.Format_ARGB32)
        # gDPSetPrimColor(POLY_OPA_DISP++, 0, 0, 235, 235, 235, pauseCtx->alpha);
        image.fill(QColor(235, 235, 235, 255))
        image.setAlphaChannel(mask)
        return QPixmap(image)


clouds = Clouds()


def get_map_point_name_path(index):
    with open(f'{oot}/{map_name_static_c}', 'rt') as f:
        c = f.read()

    ms = list(re.finditer(r'^#include "([^"]*?\.inc\.c)"', c, re.MULTILINE))
    m = ms[index]
    path = m.group(1)
    path = path.replace('.inc.c', '.png')
    if path.startswith('assets'):
        path = f'{oot}/{path}'
    return path


def find_map_point_conditions(index):
    with open(f'{oot}/src/overlays/misc/ovl_kaleido_scope/z_kaleido_scope_PAL.c', 'rt') as f:
        c = f.read()

    chunks = re.split(r' *\n *\n', c)
    needle = f'pauseCtx->worldMapPoints[{index}] = '
    chunks = [x for x in chunks if needle in x]
    return chunks


class CloudItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, cloud):
        super().__init__(pixmap)
        self.cloud = cloud


class AreaBoxItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, box):
        super().__init__(pixmap)
        self.box = box

        self.tinted = QImage(pixmap)
        self.mask = QImage(self.tinted)

        p = QPainter()
        p.begin(self.mask)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(self.mask.rect(), QColor(0,255,255,255))
        p.end()

        p.begin(self.tinted)
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.drawImage(0, 0, self.mask)
        p.end()

        self.selected_pixmap = QPixmap(self.tinted)
        self.pixmap = pixmap

    def paint(self, painter, option, widget):
        if self.isSelected():
            self.setPixmap(self.selected_pixmap)
            super().paint(painter, option, widget)
            self.setPixmap(self.pixmap)
        else:
            super().paint(painter, option, widget)


class DotItem(QGraphicsPixmapItem):
    def __init__(self, pixmap):
        super().__init__(pixmap)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

    def itemChange(self, change, value):
        # Restrict items moving past each other on X axis; they
        # need to stay sorted.
        if change == self.ItemPositionChange:
            if self.scene() and window.dots:

                def newx(item):
                    if item is self:
                        return value.x()
                    else:
                        return item.pos().x()

                xs = [newx(item) for item in window.dots]
                print(xs)
                is_sorted = all(xs[i] <= xs[i+1] for i in range(len(xs) - 1))
                if not is_sorted:
                    return QPointF(self.pos().x(), value.y())

        return super().itemChange(change, value)


class GraphicsView(QGraphicsView):
    mouse_released = pyqtSignal()
    def mouseReleaseEvent(self, x):
        super().mouseReleaseEvent(x)
        self.mouse_released.emit()


class GraphicsViewExample(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_name_path = None

        self.setWindowTitle("World Map Editor")

        self.dots = []

        self.code_font = QFont("Monaco", 8)

        self.tables = [ui_labels]

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        self.setCentralWidget(central)

        self.graphics_view = GraphicsView(self)
        self.graphics_view.setDragMode(QGraphicsView.RubberBandDrag)
        self.graphics_view.mouse_released.connect(self.mouse_released)
        layout.addWidget(self.graphics_view)

        self.sidebar = QWidget(self)
        self.sidebar.setFixedWidth(300)
        layout.addWidget(self.sidebar)
        sidebar_layout = self.sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setAlignment(Qt.AlignTop)
        sidebar_layout.setContentsMargins(0,0,0,0)

        self.filters = QWidget(self)
        sidebar_layout.addWidget(self.filters)

        filters_layout = QHBoxLayout(self.filters)
        filters_layout.setAlignment(Qt.AlignLeft)
        filters_layout.setContentsMargins(0,10,0,0)
        show_dots = QCheckBox("Dots", self)
        show_dots.setCheckState(2)
        filters_layout.addWidget(show_dots)
        show_dots.stateChanged.connect(self.show_dots)
        show_boxes = QCheckBox("Boxes", self)
        show_boxes.setCheckState(2)
        show_boxes.stateChanged.connect(self.show_boxes)
        filters_layout.addWidget(show_boxes)
        show_clouds = QCheckBox("Clouds", self)
        show_clouds.setCheckState(2)
        show_clouds.stateChanged.connect(self.show_clouds)
        filters_layout.addWidget(show_clouds)
        sidebar_layout.addWidget(self.filters)

        for table in self.tables:
            show = QCheckBox(table.name, self)
            show.setCheckState(2)
            show.stateChanged.connect(lambda state: self.show_table(table, state))
            filters_layout.addWidget(show)

        self.inspector_container = QWidget(self)
        sidebar_layout.addWidget(self.inspector_container)
        self.inspector = None

        # Create a QGraphicsScene
        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)

        self.scene.selectionChanged.connect(self.on_selection_changed)

        map = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_image.ci8.png')
        map_item = QGraphicsPixmapItem(map)
        map_item.setScale(global_scale)
        self.scene.addItem(map_item)

        dot = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_dot.ia8.png')

        self.load_clouds()
        self.load_area_boxes()

        for table in self.tables:
            self.load(table)

        # Dots
        self.dot_item_positions = []
        for x, y in list(zip(aco, bco))[16:16+12]:
            if x >= 0x8000: x -= 65536
            if y >= 0x8000: y -= 65536

            y*=-1

            x+=global_offset[0]
            y+=global_offset[1]

            dot_item = DotItem(dot)
            pos = (x*global_scale, y*global_scale)
            self.dot_item_positions.append(pos)
            dot_item.setPos(pos[0], pos[1])
            dot_item.setScale(global_scale)
            self.scene.addItem(dot_item)
            self.dots.append(dot_item)

    def show_dots(self, show):
        for item in self.scene.items():
            if isinstance(item, DotItem):
                item.setVisible(show)

    def show_boxes(self, show):
        for item in self.scene.items():
            if isinstance(item, AreaBoxItem):
                item.setVisible(show)

    def show_clouds(self, show):
        for item in self.scene.items():
            if isinstance(item, CloudItem):
                item.setVisible(show)

    def show_table(self, table, show):
        for item in self.scene.items():
            if hasattr(item, 'table') and item.table is table:
                item.setVisible(show)

    def load_area_boxes(self):

        selected_boxes = [item.box for item in self.scene.selectedItems() if isinstance(item, AreaBoxItem)]

        for item in self.scene.items():
            if isinstance(item, AreaBoxItem):
                self.scene.removeItem(item)
                
        # Area boxes
        for box in area_boxes.boxes:
            pixmap = area_boxes.get_box_texture(box.texture_index)
            item = AreaBoxItem(pixmap, box)
            item.setFlag(QGraphicsItem.ItemIsSelectable)
            item.setFlag(QGraphicsItem.ItemIsMovable)
            x, y = box.pos
            y*=-1
            x+=global_offset[0]
            y+=global_offset[1]

            pos = (x*global_scale, y*global_scale)
            item.setPos(pos[0], pos[1])
            item.setScale(global_scale)
            item.setSelected(box in selected_boxes)
            self.scene.addItem(item)

    def load(self, table):

        old_items = [
            item.cloud
            for item in self.scene.selectedItems()
            if hasattr(item, 'table') and item.table is table
        ]

        selected_rows = [
            item.data
            for item in old_items
            if item.isSelected()
        ]

        for item in old_items:
            self.scene.removeItem(item)

        for data in table.objects:
            pixmap = data.texture
            item = DataItem(data, pixmap)
            item.table = table
            x, y = data.pos
            y*=-1
            x+=global_offset[0]
            y+=global_offset[1]

            pos = (x*global_scale, y*global_scale)
            item.setPos(pos[0], pos[1])
            item.setScale(global_scale)
            item.setSelected(data in selected_rows)
            self.scene.addItem(item)

        
    def load_clouds(self):
        selected_clouds = [item.cloud for item in self.scene.selectedItems() if isinstance(item, CloudItem)]

        for item in self.scene.items():
            if isinstance(item, CloudItem):
                self.scene.removeItem(item)

        for cloud in clouds.clouds:
            pixmap = clouds.get_cloud_texture(cloud.texture_index)
            item = CloudItem(pixmap, cloud)
            item.setFlag(QGraphicsItem.ItemIsSelectable)
            item.setFlag(QGraphicsItem.ItemIsMovable)
            x, y = cloud.pos
            y*=-1
            x+=global_offset[0]
            y+=global_offset[1]

            pos = (x*global_scale, y*global_scale)
            item.setPos(pos[0], pos[1])
            item.setScale(global_scale)
            item.setSelected(cloud in selected_clouds)
            print("Add cloud", cloud)
            self.scene.addItem(item)


    def mouse_released(self):
        new_positions = [(item.pos().x(), item.pos().y()) for item in self.dots]
        if new_positions != self.dot_item_positions:
            self.dot_item_positions = new_positions

            c_positions = [
                (int(pos[0] / global_scale - global_offset[0]),
                 -int(pos[1] / global_scale - global_offset[1]))
                for pos in new_positions
            ]

            path = 'src/overlays/misc/ovl_kaleido_scope/z_kaleido_scope_PAL.c'
            diff_x = z64c.CArrayRange(
                path=path,
                decl='D_8082AEC0', # World Map Sprites X
                index=16,
                replace_count=12,
                value=[p[0] for p in c_positions]
            )
            diff_y = z64c.CArrayRange(
                path=path,
                decl='D_8082AF78', # World Map Sprites Y
                index=16,
                replace_count=12,
                value=[p[1] for p in c_positions]
            )
            z64c.install_diffs(oot, [diff_x, diff_y])

    def on_selection_changed(self):
        selected_items = self.scene.selectedItems()
        if len(selected_items) == 1:
            item = selected_items[0]

            for other in self.scene.items():
                other.setZValue(0)
            item.setZValue(1)

            self.make_inspector(item)
        else:
            self.make_inspector(None)


    def get_custom_name_path(self):
        i = self.index
        return f'{oot}/assets/textures/map_name_static/_custom_point{i}_name_eng.ia4.png'

    @pyqtSlot(str)
    def text_edited(self, new_text):
        if self.current_name_path:
            path = self.get_custom_name_path()

            print('do render', path)
            render_text(new_text, (128, 16), path)

            image = QPixmap(path)
            self.new_name_label.setPixmap(image)

    def load_name_image(self):
        selected_items = self.scene.selectedItems()

        if selected_items:
            item = selected_items[0]
            index = self.dots.index(item)
            self.index = index

            path = get_map_point_name_path(index)
            self.current_name_path = path
            
            image = QPixmap(path)
            self.name_label.setPixmap(image)
        else:
            self.name_label.setText("")

    def use_new_name(self):
        path = self.get_custom_name_path()
        path = os.path.relpath(path, oot)
        path_c = path.replace('.png', '.inc.c')
        diff = z64c.ReplaceIncludes(
            path=map_name_static_c,
            first_index=self.index,
            includes=[path_c],
            names=[f'gPoint{self.index}NameENGTex']
        )
        z64c.install_diffs(oot, [diff])
        self.load_name_image()

    def make_inspector(self, item):
        if self.inspector:
            self.inspector.deleteLater()

        inspector = self.inspector = QWidget()
        layout = QVBoxLayout(inspector)
        layout.setContentsMargins(0,0,0,0)
        self.sidebar_layout.addWidget(inspector)

        if item is None:
            pass
        elif isinstance(item, DotItem):
            index = self.dots.index(item)

            # Add a text field (line edit) to the sidebar
            self.label = QLabel()
            self.label.setText(f"Map dot {index}")
            layout.addWidget(self.label)

            self.name_label = QLabel()
            self.name_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.name_label)
            self.load_name_image()

            # Change the name
            self.text_field = QLineEdit()
            layout.addWidget(self.text_field)
            self.text_field.textEdited.connect(self.text_edited)

            self.new_name_label = QLabel()
            self.new_name_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.new_name_label)

            self.use_name_btn = QPushButton("Use")
            self.use_name_btn.clicked.connect(self.use_new_name)
            layout.addWidget(self.use_name_btn)

            self.conditions_widget = QWidget()
            self.conditions_layout = QVBoxLayout(self.conditions_widget)
            self.conditions_layout.setContentsMargins(0,0,0,0)
            layout.addWidget(self.conditions_widget)

            self.conditions_layout.addWidget(QLabel("Conditions:"))
            for chunk in find_map_point_conditions(self.index):
                w = QLabel()
                w.setFont(self.code_font)
                w.setText(textwrap.dedent(chunk))
                self.conditions_layout.addWidget(w)

        elif isinstance(item, AreaBoxItem):
            index = item.box.texture_index
            label = QLabel()
            layout.addWidget(label)
            label.setText(f"Area box {item.box.index}")

            combo = QComboBox(self)
            for i, x in enumerate(area_boxes.texture_sizes):
                combo.addItem(f"Type {i+1} ({x[0]}×{x[1]})")
            layout.addWidget(combo)

            def on_change(i):
                item.box.texture_index = i
                self.load_area_boxes()
            combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(on_change)

            label = QLabel()
            label.setText("Scenes in this area:")
            layout.addWidget(label)

            label = QLabel()
            label.setFont(self.code_font)
            layout.addWidget(label)
            label.setText('\n'.join(
                area_scenes.scenes_by_area.get(item.box.index, [])
            ))

        elif isinstance(item, CloudItem):
            cloud = item.cloud
            label = QLabel()
            layout.addWidget(label)
            label.setText(f"Cloud {cloud.index}")

            label = QLabel()
            layout.addWidget(label)
            label.setText(f"Covers area {cloud.flag}")

            label = QLabel()
            label.setFont(self.code_font)
            layout.addWidget(label)
            label.setText('\n'.join(
                area_scenes.scenes_by_area.get(cloud.flag, [])
            ))


window = GraphicsViewExample()
window.show()
sys.exit(app.exec_())
