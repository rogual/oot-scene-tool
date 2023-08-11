import sys
import os
import re
import glob
import pathlib
import textwrap
import functools
import collections

from dataclasses import dataclass

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

map_name_static_c = 'assets/textures/map_name_static/map_name_static.c'
kaleido_map_c = 'src/overlays/misc/ovl_kaleido_scope/z_kaleido_map_PAL.c'
kaleido_scope_c = 'src/overlays/misc/ovl_kaleido_scope/z_kaleido_scope_PAL.c'

langs = ['eng', 'ger', 'fra']

box_tint = QColor(100, 255,255,255)
name_tint = QColor(150,255,255,255)


def get_nth_include_as_png(c_path, i):
    with open(f'{oot}/{c_path}', 'rt') as f:
        c = f.read()

    ms = list(re.finditer(r'^#include "([^"]*?\.inc\.c)"', c, re.MULTILINE))
    m = ms[i]
    path = m.group(1)
    path = path.replace('.inc.c', '.png')
    return path


def tint_pixmap(pixmap, color):
    tinted = QImage(pixmap)
    mask = QImage(tinted)

    p = QPainter()
    p.begin(mask)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(mask.rect(), color)
    p.end()

    p.begin(tinted)
    p.setCompositionMode(QPainter.CompositionMode_Multiply)
    p.drawImage(0, 0, mask)
    p.end()

    return QPixmap(tinted)


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
    """
    Every object in the world map except for the area boxes has its position
    stored in a few arrays, which we'll call “sprite arrays”. These then
    get expanded to quads and put into the kaleidoscope vertex arrays.

    This class can read the sprites, assign 'kinds' to them, and save back
    their positions.
    """
    def __init__(self):
        # There's a decomp PR to give them proper names, but for now the
        # sprite arrays just have these D_ identifiers.
        pos_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AEC0')
        pos_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AF78')
        size_x = z64c.read_array(oot, kaleido_scope_c, 'D_8082AAEC')
        size_y = z64c.read_array(oot, kaleido_scope_c, 'D_8082AB2C')

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
        diff_x = z64c.CArray(
            path=kaleido_scope_c,
            decl='D_8082AEC0',  # World Map Sprites X
            value=[sprite.pos[0] for sprite in self.objects]
        )
        diff_y = z64c.CArray(
            path=kaleido_scope_c,
            decl='D_8082AF78',  # World Map Sprites Y
            value=[sprite.pos[1] for sprite in self.objects]
        )
        z64c.install_diffs(oot, [diff_x, diff_y])

sprites = Sprites()


class DataItem(QGraphicsPixmapItem):
    """QGraphicsItem representing an editable thing in the world map."""
    def __init__(self, data, pixmap):
        super().__init__(pixmap)
        self.data = data
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)


class Table:
    """
    This editor is organized into "tables", which work a bit like database
    tables, except instead of a database, we're reading and writing from
    the OOT decomp repo.

    Each table handles a different kind of editable thing:
    - Map Dots
    - Area Boxes
    - Clouds
    - UI Labels

    """
    item_class = DataItem


@dataclass
class SpriteRef:
    """
    Data objects that are represented by sprites. They just reference an
    underlying Sprite and use its pos and size.
    """
    sprite: object

    @property
    def pos(self):
        return self.sprite.pos

    @property
    def size(self):
        return self.sprite.size


@dataclass
class UILabelCurrentPositionLabel(SpriteRef):
    language_index: int = 0

    @property
    def texture(self):
        return ui_labels.current_position_labels[self.language_index]

    def inspect(self, layout):
        layout.addWidget(QLabel("Current Position Label"))

        combo = QComboBox()
        for i, lang in enumerate(langs):
            combo.addItem(lang)
        layout.addWidget(combo)

        combo.setCurrentIndex(self.language_index)
        combo.currentIndexChanged.connect(self.set_language_index)

    def set_language_index(self, index):
        self.language_index = index
        window.load(ui_labels)


@dataclass
class UILabelPlaceName(SpriteRef):
    language_index: int = 0
    area_index: int = 0

    @property
    def texture(self):
        return ui_labels.place_name_texture(self.area_index, self.language_index)

    def inspect(self, layout):

        layout.addWidget(QLabel("Current Area Name"))

        combo = QComboBox()
        for i, lang in enumerate(langs):
            combo.addItem(lang)
        layout.addWidget(combo)

        combo.setCurrentIndex(self.language_index)
        combo.currentIndexChanged.connect(self.set_language_index)

        layout.addWidget(QLabel("Preview Area"))
        x = QSpinBox()
        x.setMinimum(0)
        x.setMaximum(21)
        x.setValue(self.area_index)
        x.valueChanged.connect(self.set_area_index)
        layout.addWidget(x)

    def set_language_index(self, index):
        self.language_index = index
        window.load(ui_labels)

    def set_area_index(self, index):
        self.area_index = index
        window.load(ui_labels)


class UILabels(Table):
    """
    There are only two UI labels:
    - The "Current Position" label
    - The name of the current area just below it.
    """
    name = "UI Labels"

    current_position_labels = [
        load_mask(
            f'{oot}/assets/textures/icon_item_{nlang}_static/'
            f'pause_current_position_{lang}.i4.png',
            QColor(0, 0, 0, 255)
        )
        for nlang, lang in [('nes', 'eng'), ('ger', 'ger'), ('fra', 'fra')]
    ]

    def __init__(self):
        self.objects = [
            UILabelPlaceName(sprite=sprite)
            for sprite in sprites.objects_of_kind('place_name')
        ] + [
            UILabelCurrentPositionLabel(sprite=sprite)
            for sprite in sprites.objects_of_kind('current_position_label')
        ]

    def set_and_save_positions(self, positions):
        for o, pos in zip(self.objects, positions):
            o.sprite.pos = pos
        sprites.save_positions()

    def place_name_texture(self, area_index, language_index):
        png_path = get_nth_include_as_png(
            map_name_static_c,
            36 +
            22 * language_index +
            area_index
        )
        png_path = f'{oot}/{png_path}'
        return tint_pixmap(QPixmap(png_path), name_tint)

    def area_selected(self, index):
        for object in self.objects:
            if isinstance(object, UILabelPlaceName):
                object.set_area_index(index)

ui_labels = UILabels()


class AreaBoxItem(DataItem):
    def __init__(self, box, pixmap):
        super().__init__(box, pixmap)
        self.box = box

        self.selected_pixmap = tint_pixmap(pixmap, box_tint)
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

    def on_select(self):
        ui_labels.area_selected(self.index)

    def name_texture_changed(self):
        window.load(ui_labels)

    def inspect(self, layout):
        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Area box {self.index}")

        # Box size selector
        combo = QComboBox()
        for i, x in enumerate(area_boxes.texture_sizes):
            combo.addItem(f"{x[0]}×{x[1]}")
        layout.addWidget(combo)
        combo.setCurrentIndex(self.texture_index)
        combo.currentIndexChanged.connect(self.change_type)

        # Area name
        name_edit = NameTextureEditor(
            map_name_static_c,
            36 + self.index,
            f'gArea{self.index}PositionNameENGTex',
            (
                f'{oot}/assets/textures/map_name_static/'
                f'_custom_area{self.index}_position_name_eng.ia8.png'
            ),
            (80, 32),
            text_params={
                'typeface': 'rocknroll',
                'stroke_width': 4
            }
        )
        name_edit.saved.connect(self.name_texture_changed)
        layout.addWidget(name_edit)

        # Scene List
        label = QLabel()
        label.setText("Scenes in this area:")
        layout.addWidget(label)

        label = QLabel()
        label.setFont(window.code_font)
        label.setText('\n'.join(
            area_scenes.scenes_by_area.get(self.index, [])
        ))

        area = QScrollArea()
        area.setWidget(label)
        layout.addWidget(area)


class AreaBoxes:
    """
    Boxes that show where the current area is on the map. One per
    area. Only one is ever shown at a time.
    """
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
        return (
            f'{oot}/assets/textures/icon_item_field_static/'
            f'world_map_area_box_{index+1}.ia4.png'
        )

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


class Clouds(Table):
    """
    Clouds that cover map areas until the player visits them. Each
    one has a “flag” which is just the ID of the area it covers.
    """
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
        return (
            f'{oot}/assets/textures/icon_item_field_static/'
            f'world_map_cloud_{index+1}.i4.png'
        )

    @functools.cache
    def get_cloud_texture(self, index):
        return load_mask(self.get_cloud_texture_path(index), QColor(235, 235, 235, 255))

    def set_and_save_positions(self, positions):
        for o, new_pos in zip(self.objects, positions):
            o.sprite.pos = new_pos
        sprites.save_positions()


@dataclass
class Cloud(SpriteRef):
    index: int
    texture_index: int
    flag: int

    @property
    def texture(self):
        return clouds.get_cloud_texture(self.texture_index)

    def inspect(cloud, layout):
        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Cloud {cloud.index}")

        label = QLabel()
        layout.addWidget(label)
        label.setText(f"Covers area {cloud.flag}")

        # Scene list  
        label = QLabel()
        label.setFont(window.code_font)
        label.setText('\n'.join(
            area_scenes.scenes_by_area.get(cloud.flag, [])
        ))

        area = QScrollArea()
        area.setWidget(label)
        layout.addWidget(area)

    def on_select(self):
        ui_labels.area_selected(self.flag)


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
class Dot(SpriteRef):
    dot_index: int

    @property
    def texture(self):
        return Dots.texture

    def inspect(self, layout):
        index = self.dot_index

        # Add a text field (line edit) to the sidebar
        label = QLabel()
        label.setText(f"Map dot {index}")
        layout.addWidget(label)

        name_edit = NameTextureEditor(
            map_name_static_c,
            index,
            f'gPoint{index}NameENGTex',
            (
                f'{oot}/assets/textures/map_name_static/'
                f'_custom_point{index}_name_eng.ia4.png'
            ),
            (128, 16),
        )
        layout.addWidget(name_edit)

        conditions_widget = QWidget()
        conditions_layout = QVBoxLayout(conditions_widget)
        conditions_layout.setContentsMargins(0,0,0,0)

        conditions_layout.addWidget(QLabel("Conditions:"))
        for chunk in find_map_point_conditions(index):
            w = QLabel()
            w.setFont(window.code_font)
            w.setText(textwrap.dedent(chunk))
            conditions_layout.addWidget(w)

        area = QScrollArea()
        area.setWidget(conditions_widget)
        layout.addWidget(area)


class Dots(Table):
    """
    Dots on the world map. These aren't connected at all to scenes or areas. Each
    dot just has a position and a bunch of if-statements in z_kaleido_scope_PAL.c
    that determine whether to show the dot and whether to highlight it in some way.

    Each dot also has a name texture, which is shown underneath the map when you
    select that dot on the pause screen.

    Dots are ordered left-to-right, and if you rearrange them, it'll break the
    navigation on the pause screen. It's tricky to rearrange them properly, because
    you'd have to go in and change all the conditions in the code too. So, we just
    disallow moving dots past each other on the X axis.
    """
    name = "Dots"
    item_class = DotItem
    texture = QPixmap(
        f'{oot}/assets/textures/icon_item_field_static/world_map_dot.ia8.png'
    )

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


def find_map_point_conditions(index):
    with open(f'{oot}/{kaleido_scope_c}', 'rt') as f:
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


class NameTextureEditor(QWidget):
    """
    GUI for editing name textures of dots and areas.
    """
    saved = pyqtSignal()

    def __init__(self, c_path, include_index, decl, custom_path, size, text_params={}, *a, **kw):
        super().__init__(*a, *kw)
        self.custom_path = custom_path
        self.c_path = c_path
        self.size = size
        self.include_index = include_index
        self.decl = decl
        self.text_params = text_params

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)
        self.load_name_image()

        text_field = QLineEdit()
        layout.addWidget(text_field)
        text_field.textEdited.connect(self.text_edited)

        new_name_label = self.new_name_label = QLabel()
        new_name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(new_name_label)

        use_name_btn = self.use_name_btn = QPushButton("Use")
        use_name_btn.clicked.connect(self.use_new_name)
        use_name_btn.setEnabled(False)
        layout.addWidget(use_name_btn)

    def get_path_from_c(self):
        path = get_nth_include_as_png(self.c_path, self.include_index)
        if path.startswith('assets'):
            path = f'{oot}/{path}'
        return path

    def load_name_image(self):
        image = QPixmap(self.get_path_from_c())
        self.name_label.setPixmap(image)

    def use_new_name(self):
        path = self.custom_path
        path = os.path.relpath(path, oot)
        path_c = path.replace('.png', '.inc.c')
        diff = z64c.ReplaceIncludes(
            path=self.c_path,
            first_index=self.include_index,
            includes=[path_c],
            names=[self.decl]
        )
        z64c.install_diffs(oot, [diff])
        self.load_name_image()
        self.saved.emit()

    def text_edited(self, new_text):
        self.use_name_btn.setEnabled(new_text != '')
        render_text(new_text, self.size, self.custom_path, **self.text_params)

        image = QPixmap(self.custom_path)
        self.new_name_label.setPixmap(image)


class WorldMapEditor(QMainWindow):
    def __init__(self):
        super().__init__()

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
            y *= -1
            x += global_offset[0]
            y += global_offset[1]

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

            if isinstance(item, DataItem):
                if hasattr(item.data, 'on_select'):
                    item.data.on_select()

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


if __name__ == '__main__':
    window = WorldMapEditor()
    window.show()
    sys.exit(app.exec_())
