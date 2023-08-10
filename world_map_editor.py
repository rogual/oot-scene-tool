import sys
import os
import re
import textwrap
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from .text import render_text
from . import z64c

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

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        self.setCentralWidget(central)

        self.graphics_view = GraphicsView(self)
        self.graphics_view.mouse_released.connect(self.mouse_released)
        layout.addWidget(self.graphics_view)

        self.sidebar = QWidget(self)
        self.sidebar.setFixedWidth(300)
        layout.addWidget(self.sidebar)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setAlignment(Qt.AlignTop)
        sidebar_layout.setContentsMargins(0,0,0,0)

        # Add a text field (line edit) to the sidebar
        self.label = QLabel()
        sidebar_layout.addWidget(self.label)

        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.name_label)

        # Change the name
        self.text_field = QLineEdit()
        sidebar_layout.addWidget(self.text_field)
        self.text_field.textEdited.connect(self.text_edited)

        self.new_name_label = QLabel()
        self.new_name_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.new_name_label)

        self.use_name_btn = QPushButton("Use")
        self.use_name_btn.clicked.connect(self.use_new_name)
        sidebar_layout.addWidget(self.use_name_btn)

        self.conditions_widget = QWidget()
        self.conditions_layout = QVBoxLayout(self.conditions_widget)
        self.conditions_layout.setContentsMargins(0,0,0,0)
        sidebar_layout.addWidget(self.conditions_widget)

        # Create a QGraphicsScene
        self.scene = QGraphicsScene()
        self.graphics_view.setScene(self.scene)

        self.scene.selectionChanged.connect(self.on_select_dot)

        map = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_image.ci8.png')
        map_item = QGraphicsPixmapItem(map)
        map_item.setScale(global_scale)
        self.scene.addItem(map_item)

        dot = QPixmap(f'{oot}/assets/textures/icon_item_field_static/world_map_dot.ia8.png')

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

        self.setGeometry(100, 100, 400, 300)

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

    def on_select_dot(self):
        self.load_name_image()

        self.new_name_label.setPixmap(QPixmap())
        self.text_field.setText("")

        # seriously
        layout = self.conditions_layout
        while layout.count() > 0: 
            layout.itemAt(0).widget().setParent(None)

        self.conditions_layout.addWidget(QLabel("Conditions:"))

        print('--- chunks ---')
        for chunk in find_map_point_conditions(self.index):
            w = QLabel()
            w.setFont(self.code_font)
            w.setText(textwrap.dedent(chunk))
            self.conditions_layout.addWidget(w)
        
        selected_items = self.scene.selectedItems()
        if selected_items:
            item = selected_items[0]
            index = self.dots.index(item)
            self.label.setText(f"Map dot {index}")

        else:
            self.label.setText("Nothing selected.")
            self.current_name_path = None

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

app = QApplication(sys.argv)
window = GraphicsViewExample()
window.show()
sys.exit(app.exec_())
