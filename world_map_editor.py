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
window = None

global_scale = 3
global_offset = (108, 58)

oot = '/Users/me/Projects/Contrib/oot'

'''
12 map points
Flags in worldMapPoints[]
Positions in mapPageVtx[124 + i * 4], 4 verts each
'''


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

    def inspect(self, layout):
        pass

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

    def objects_of_kind(self, kind):
        if isinstance(kind, str):
            kind = (kind,)
        return [x for x in self.objects if x.kind in kind]

    def save_positions(self):
        path = 'src/overlays/misc/ovl_kaleido_scope/z_kaleido_scope_PAL.c'
        diff_x = z64c.CArray(
            path=path,
            decl='D_8082AEC0', # World Map Sprites X
            value=[sprite.pos[0] for sprite in self.objects]
        )
        diff_y = z64c.CArray(
            path=path,
            decl='D_8082AF78', # World Map Sprites Y
            value=[sprite.pos[1] for sprite in self.objects]
        )
        z64c.install_diffs(oot, [diff_x, diff_y])

sprites = Sprites()


class DataItem(QGraphicsPixmapItem):
    def __init__(self, data, pixmap):
        super().__init__(pixmap)
        self.data = data
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)


class Table:
    item_class = DataItem


@dataclass
class UILabel:
    sprite: object
    preview_index: int

    @property
    def texture(self):
        if self.sprite.kind == 'place_name':
            return ui_labels.place_name_texture

        if self.sprite.kind == 'current_position_label':
            return ui_labels.current_position_labels[self.preview_index]

    @property
    def pos(self):
        return self.sprite.pos

    @property
    def size(self):
        return self.sprite.size

    def inspect(self, layout):
        if self.sprite.kind == 'place_name':
            layout.addWidget(QLabel("Current Place Name"))

        if self.sprite.kind == 'current_position_label':
            layout.addWidget(QLabel("Current Position Label"))

            langs = ['eng', 'fra', 'ger']

            combo = QComboBox()
            for i, lang in enumerate(langs):
                combo.addItem(lang)
            layout.addWidget(combo)

            combo.setCurrentIndex(self.preview_index)
            combo.currentIndexChanged.connect(self.set_preview_index)

    def set_preview_index(self, index):
        self.preview_index = index
        window.load(ui_labels)
    

class UILabels(Table):
    name = "UI Labels"

    current_position_labels = [
        load_mask(f'{oot}/assets/textures/icon_item_{nlang}_static/pause_current_position_{lang}.i4.png', QColor(0, 0, 0, 255))
        for nlang, lang in [('nes', 'eng'), ('fra', 'fra'), ('ger', 'ger')]
    ]

    place_name_texture = QPixmap(
        f'{oot}/assets/textures/map_name_static/kakariko_village_position_name_eng.ia8.png'
    )

    def __init__(self):
        self.objects = [
            UILabel(sprite=sprite, preview_index=0)
            for sprite in sprites.objects_of_kind(('place_name', 'current_position_label'))
        ]

    def set_and_save_positions(self, positions):
        for o, pos in zip(self.objects, positions):
            o.sprite.pos = pos
        sprites.save_positions()

ui_labels = UILabels()


class AreaBoxItem(DataItem):
    def __init__(self, box, pixmap):
        super().__init__(box, pixmap)
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


@dataclass
class AreaBox:
    index: int
    pos: object
    size: object
    texture_index: int

    @property
    def texture(self):
        return area_boxes.get_box_texture(self.texture_index)

    def change_type(self, index):
        self.texture_index = index
        window.load(area_boxes)

    def inspect(self, layout):
        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Area box {self.index}")

        combo = QComboBox()
        for i, x in enumerate(area_boxes.texture_sizes):
            combo.addItem(f"Type {i+1} ({x[0]}×{x[1]})")
        layout.addWidget(combo)

        combo.setCurrentIndex(self.texture_index)
        combo.currentIndexChanged.connect(self.change_type)

        label = QLabel()
        label.setText("Scenes in this area:")
        layout.addWidget(label)

        label = QLabel()
        label.setFont(window.code_font)
        layout.addWidget(label)
        label.setText('\n'.join(
            area_scenes.scenes_by_area.get(self.index, [])
        ))
    

class AreaBoxes:
    name = "Boxes"
    item_class = AreaBoxItem

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

        self.objects = [
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

    def set_and_save_positions(self, positions):
        for o, pos in zip(self.objects, positions):
            o.pos = pos

        diff_x = z64c.CArray(
            path=kaleido_map_c,
            decl='areaBoxPosX',
            value=[o.pos[0] for o in self.objects]
        )
        diff_y = z64c.CArray(
            path=kaleido_map_c,
            decl='areaBoxPosY',
            value=[o.pos[1] for o in self.objects]
        )
        z64c.install_diffs(oot, [diff_x, diff_y])


area_boxes = AreaBoxes()


@dataclass
class Cloud:
    sprite: object
    index: int
    texture_index: int
    flag: int

    @property
    def texture(self):
        return clouds.get_cloud_texture(self.texture_index)

    @property
    def pos(self):
        return self.sprite.pos

    @property
    def size(self):
        return self.sprite.size

    def inspect(cloud, layout):
        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Cloud {cloud.index}")

        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Covers area {cloud.flag}")

        label = QLabel()
        label.setFont(window.code_font)
        layout.addWidget(label)
        label.setText('\n'.join(
            area_scenes.scenes_by_area.get(cloud.flag, [])
        ))


class Clouds(Table):
    name = "Clouds"
    def __init__(self):
        cloud_sprites = sprites.objects_of_kind('cloud')
        tex = z64c.read_array(oot, kaleido_map_c, 'cloudTexs')
        flags = z64c.read_array(oot, kaleido_map_c, 'cloudFlagNums')

        texture_indices = [
            int(re.match(r'gWorldMapCloud(\d+)Tex', x).group(1)) - 1
            for x in tex
        ]

        self.objects = [
            Cloud(
                sprite=sprite,
                index=i,
                texture_index=texture_index,
                flag=flag
            )
            for i, (sprite, texture_index, flag) in enumerate(zip(
                    cloud_sprites,
                    texture_indices,
                    flags
            ))
        ]

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

    def set_and_save_positions(self, positions):
        for o, new_pos in zip(self.objects, positions):
            o.sprite.pos = new_pos
        sprites.save_positions()

clouds = Clouds()


class DotItem(DataItem):
    def __init__(self, data, pixmap):
        super().__init__(data, pixmap)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

    def itemChange(self, change, value):
        # Restrict items moving past each other on X axis; they
        # need to stay sorted.
        if change == self.ItemPositionChange and window:

            dot_items = [
                x for x in window.scene.items()
                if hasattr(x, 'table') and x.table is dots
            ]

            def item_for_dot(dot):
                return next(x for x in dot_items if x.data is dot)

            dot_items = [item_for_dot(x) for x in dots.objects]

            if self.scene() and dot_items:

                def newx(item):
                    if item is self:
                        return value.x()
                    else:
                        return item.pos().x()

                xs = [newx(item) for item in dot_items]
                is_sorted = all(xs[i] <= xs[i+1] for i in range(len(xs) - 1))
                if not is_sorted:
                    return QPointF(self.pos().x(), value.y())

        return super().itemChange(change, value)



@dataclass
class Dot:
    sprite: object
    dot_index: int

    @property
    def texture(self):
        return Dots.texture

    @property
    def pos(self):
        return self.sprite.pos

    @property
    def size(self):
        return self.sprite.size

    def inspect(self, layout):
        index = self.dot_index

        # Add a text field (line edit) to the sidebar
        label = QLabel()
        label.setText(f"Map dot {index}")
        layout.addWidget(label)

        name_label = self.name_label = QLabel()
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        self.load_name_image()

        # Change the name
        text_field = QLineEdit()
        layout.addWidget(text_field)
        text_field.textEdited.connect(self.text_edited)

        new_name_label = self.new_name_label = QLabel()
        new_name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(new_name_label)

        use_name_btn = QPushButton("Use")
        use_name_btn.clicked.connect(self.use_new_name)
        layout.addWidget(use_name_btn)

        conditions_widget = QWidget()
        conditions_layout = QVBoxLayout(conditions_widget)
        conditions_layout.setContentsMargins(0,0,0,0)
        layout.addWidget(conditions_widget)

        conditions_layout.addWidget(QLabel("Conditions:"))
        for chunk in find_map_point_conditions(index):
            w = QLabel()
            w.setFont(window.code_font)
            w.setText(textwrap.dedent(chunk))
            conditions_layout.addWidget(w)

    def get_custom_name_path(self):
        i = self.dot_index
        return f'{oot}/assets/textures/map_name_static/_custom_point{i}_name_eng.ia4.png'

    def text_edited(self, new_text):
        if self.current_name_path:
            path = self.get_custom_name_path()

            print('do render', path)
            render_text(new_text, (128, 16), path)

            image = QPixmap(path)
            self.new_name_label.setPixmap(image)

    def load_name_image(self):
        path = get_map_point_name_path(self.dot_index)
        self.current_name_path = path
            
        image = QPixmap(path)
        self.name_label.setPixmap(image)
            
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


class Dots(Table):
    name = "Dots"
    item_class = DotItem
    texture = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_dot.ia8.png')

    def __init__(self):
        self.objects = [
            Dot(
                sprite=sprite,
                dot_index=i,
            )
            for i, sprite in enumerate(sprites.objects_of_kind('point'))
        ]

    def set_and_save_positions(self, positions):
        for o, new_pos in zip(self.objects, positions):
            o.sprite.pos = new_pos
        sprites.save_positions()

dots = Dots()


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


class GraphicsView(QGraphicsView):
    mouse_released = pyqtSignal()
    def mouseReleaseEvent(self, x):
        super().mouseReleaseEvent(x)
        self.mouse_released.emit()


class WorldMapEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_name_path = None

        self.setWindowTitle("World Map Editor")

        self.code_font = QFont("Monaco", 8)

        self.tables = [clouds, area_boxes, ui_labels, dots]

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
        sidebar_layout.addWidget(self.filters)

        for table in self.tables:
            show = QCheckBox(table.name, self)
            show.setCheckState(2)
            show.stateChanged.connect(lambda state, table=table: self.show_table(table, state))
            filters_layout.addWidget(show)

        self.inspector_container = QWidget(self)
        sidebar_layout.addWidget(self.inspector_container)
        self.inspector = None

        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)

        self.scene.selectionChanged.connect(self.on_selection_changed)

        map = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_image.ci8.png')
        map_item = QGraphicsPixmapItem(map)
        map_item.setScale(global_scale)
        self.scene.addItem(map_item)

        for table in self.tables:
            self.load(table)

    def show_table(self, table, show):
        for item in self.scene.items():
            if hasattr(item, 'table') and item.table is table:
                item.setVisible(show)

    def load(self, table):
        print("Load", table.name)
        old_items = [
            item
            for item in self.scene.items()
            if hasattr(item, 'table') and item.table is table
        ]

        selected_rows = [
            item.data
            for item in old_items
            if item.isSelected()
        ]

        print("Remove", len(old_items))
        for item in old_items:
            self.scene.removeItem(item)

        items = []
        for data in table.objects:
            print("Add", data)
            pixmap = data.texture
            item = table.item_class(data, pixmap)
            items.append(item)
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

        table.loaded_positions = [(x.pos().x(), x.pos().y()) for x in items]


    def mouse_released(self):
        for table in self.tables:
            self.save_moved_items(table)


    def save_moved_items(self, table):

        def item_for(o):
            for item in self.scene.items():
                if isinstance(item, DataItem) and item.data is o:
                    return item
            raise Exception()

        table_items = [item_for(o) for o in table.objects]

        new_positions = [
            (item.pos().x(), item.pos().y())
            for item in table_items
        ]
        if new_positions != table.loaded_positions:
            print("Saving moved items for", table.name)

            table.loaded_positions = new_positions

            c_positions = [
                (int(pos[0] / global_scale - global_offset[0]),
                 -int(pos[1] / global_scale - global_offset[1]))
                for pos in new_positions
            ]

            table.set_and_save_positions(c_positions)

    def set_item_z(self, item, z):
        assert z in [0, 1]
        if hasattr(item, 'table'):
            layer = self.tables.index(item.table)
        else:
            layer = -1
        item.setZValue(layer * 2 + z)

    def on_selection_changed(self):
        selected_items = self.scene.selectedItems()
        if len(selected_items) == 1:
            item = selected_items[0]

            for other in self.scene.items():
                self.set_item_z(other, 0)
            self.set_item_z(item, 1)

            self.make_inspector(item)
        else:
            self.make_inspector(None)

    def make_inspector(self, item):
        if self.inspector:
            self.inspector.deleteLater()

        inspector = self.inspector = QWidget()
        layout = QVBoxLayout(inspector)
        layout.setContentsMargins(0,0,0,0)
        self.sidebar_layout.addWidget(inspector)

        if item is None:
            pass
        elif isinstance(item, DataItem):
            item.data.inspect(layout)


window = WorldMapEditor()
window.show()
sys.exit(app.exec_())
