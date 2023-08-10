import xml.etree.ElementTree as ET

from .common_utils import *

class Z64XML:
    def __init__(self, path):
        self.path = path
        self.doc = ET.parse(path)
        self.root = self.doc.getroot()

    def get_file(self, name):
        node = self.root.find(f'.//File[@Name="{name}"]')
        return Z64File(self, node)


class Z64File:
    def __init__(self, xml, node):
        self.xml = xml
        self.node = node

    @property
    @yield_list
    def textures(self):
        for child in self.node.findall('./Texture'):
            yield Z64Texture(self, child)


class Z64Texture:
    def __init__(self, file_, node):
        self.file = file_
        self.node = node
