import re
import shutil

from . import z64xml
from dataclasses import dataclass, field
from .common_utils import *


@dataclass
class SceneTableEntry:
    index: int
    segment: str
    title_card_segment: str
    enum_name: str
    draw_config: str
    unk1: int
    unk2: int


@dataclass
class CArray:
    path: str
    decl: str
    value: object


@dataclass
class CArrayItem:
    path: str
    decl: str
    index: int
    value: object
    format_hint: str = ''


@dataclass
class CArrayRange:
    path: str
    decl: str
    index: int
    replace_count: int
    value: object


@dataclass
class InstallFile:
    from_path: str
    to_path: str


@dataclass
class ReplaceIncludes:
    path: str
    first_index: int
    includes: list
    names: list


def read_array(oot, path, decl):
    with open(f'{oot}/{path}', 'rt') as f:
        c = f.read()
    start, end = find_c_array(c, decl)
    return from_c(c[start:end])
    

def find_c_array(c, decl):
    regex = (
        r'^(?:[A-Za-z0-9_]+\*? )*' + 
        re.escape(decl) +
        r'\[.*?\]*' +
        r'\s*=\s*\{' +
        r'(.*?)' +
        r'\}\s*;'
    )
    m = re.search(
        regex,
        c,
        flags=re.MULTILINE | re.DOTALL
    )
    if not m:
        log('==-==-==-==-==')
        log(c)
        raise Exception(
            f"'{decl}' not found"
        )

    return m.span(1)

    
@yield_list
def get_all_changes(repo_path, all_items):
    for rel_path, items in groupby(
        all_items, lambda x: x.path
    ):
        path = f'{repo_path}/{rel_path}'
        
        with open(path, 'rt') as f:
            c = f.read()

        for item in items:
            start, end = find_c_array(c, item.decl)

        array = c[start:end]

        replacement = to_c(item.value)

        c = c[:start] + replacement + c[end:]

        yield path, c


def to_c(value, format_hint=''):
    if isinstance(value, list):
        val_strs = map(to_c, value)
        if format_hint == 'floor_ids':
            val_strs = [x.rjust(4) for x in val_strs]
        return '{ ' + ', '.join(val_strs) + ' }'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return '%.1ff' % value
    if isinstance(value, str):
        return value

    raise Exception("to_c: %s" % repr(value))


def find_array_item(text, find_index):
    i = 0
    index = 0
    level = 0
    found_start = None
    found_end = None
    block_comment = False
    line_comment = False
    while i < len(text):

        char = text[i]

        if line_comment and char == '\n':
            line_comment = False
            i += 1
            continue

        if char in ' \r\n\t':
            i += 1
            continue

        if i + 1 < len(text) and char == '*' and text[i+1] == '/':
            if not block_comment:
                raise Exception("Got confused: found */ outside comment")
            block_comment = False
            i += 2
            continue

        if block_comment or line_comment:
            i += 1
            continue

        if i + 1 < len(text) and char == '/' and text[i+1] == '/':
            line_comment = True
            i += 2
            continue

        if i + 1 < len(text) and char == '/' and text[i+1] == '*':
            block_comment = True
            i += 2
            continue

        if level == 0:
            if index == find_index and found_start is None:
                found_start = i

            if char == ',':
                index += 1

            if index > find_index and found_end is None:
                found_end = i

        if char == '{':
            level += 1

        if char == '}':
            level -= 1
            if level < 0:
                raise Exception("Got confused")
            
        i += 1

    if found_start is None or found_end is None:
        return None

    return found_start, found_end
    

@yield_list
def get_scene_table(oot):
    path = f'{oot}/include/tables/scene_table.h'
    with open(path, 'rt') as f:
        text = f.read()

    for row in re.findall(rf'^/\* (0x..) \*/ DEFINE_SCENE\((.*?)\)', text, flags=re.MULTILINE):

        xs = [x.strip() for x in row[1].split(',')]
        row = [row[0]] + xs

        yield SceneTableEntry(*row)


def get_scene_table_entry(oot, enum_name):
    for x in get_scene_table(oot):
        if x.enum_name == enum_name:
            return x
    raise Exception(f'{enum_name} is not a scene')


def get_english_title_card_asset_name(oot, enum_name):
    entry = get_scene_table_entry(oot, enum_name)
    segment = entry.title_card_segment

    xml = z64xml.Z64XML(
        f'{oot}/assets/xml/textures/place_title_cards.xml'
    )
    file_ = xml.get_file(segment)
    texture = file_.textures[0]
    return texture.node.attrib['OutName']


def get_english_position_name_asset_name(oot, enum_name):
    entry = get_scene_table_entry(oot, enum_name)

    xml = z64xml.Z64XML(
        f'{oot}/assets/xml/textures/map_name_static.xml'
    )
    file_ = xml.get_file('map_name_static')

    num_point_names = 36
    texture = file_.textures[num_point_names + entry.index]

    return texture.node.attrib['OutName']
    

def get_scene_index(oot, enum_name):
    assert enum_name.startswith('SCENE_')

    path = f'{oot}/include/tables/scene_table.h'

    with open(path, 'rt') as f:
        text = f.read()
    m = re.search(rf'^/\* (0x..) \*/ DEFINE_SCENE.*{enum_name}', text, flags=re.MULTILINE)
    if not m:
        raise Exception(f"Can't find {enum_name} in {path}")

    return int(m.group(1), 0)
        

def from_c(text):
    if '"' in text or '\'' in text:
        raise Exception()
    text = text.replace('{', '[')
    text = text.replace('}', ']')
    text = re.sub('//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'[A-Za-z_][A-Za-z0-9_]+', lambda m: '"' + m.group(0) + '"', text)

    text = '[' + text + ']'
    text = text.strip()

    return eval(text)


def install_diffs(oot, diffs):
    for diff in diffs:

        if isinstance(diff, InstallFile):
            log("Install", diff.to_path)
            shutil.copyfile(diff.from_path, f'{oot}/{diff.to_path}')

        elif isinstance(diff, CArray):
            log("Write array", diff.decl)
            with open(f'{oot}/{diff.path}', 'rt') as f:
                c = f.read()
            start, end = find_c_array(c, diff.decl)

            array = to_c(diff.value)
            array = unwrap_braces(array)

            c = c[:start] + array + c[end:]

            with open(f'{oot}/{diff.path}', 'wt') as f:
                f.write(c)


        elif isinstance(diff, CArrayItem):
            log(f"Write array item {diff.decl}[{diff.index}]")

            with open(f'{oot}/{diff.path}', 'rt') as f:
                c = f.read()
                start, end = find_c_array(c, diff.decl)

                array = c[start:end]

                istart, iend = find_array_item(array, diff.index)
                array = array[:istart] + to_c(diff.value, diff.format_hint) + array[iend:]

                c = c[:start] + array + c[end:]

            with open(f'{oot}/{diff.path}', 'wt') as f:
                f.write(c)

        elif isinstance(diff, CArrayRange):
            # TODO: All this array stuff is too hacky.
            # It'll fail if the array is too short. It should be able
            # to append.

            log(f"Write array range {diff.decl} from {diff.index} count {diff.replace_count}")

            with open(f'{oot}/{diff.path}', 'rt') as f:
                c = f.read()
                start, end = find_c_array(c, diff.decl)

                array = c[start:end]

                first_index = diff.index

                log(array)
                log('AAAAAA', diff.index)
                range_start = find_array_item(array, diff.index)[0]
                log('BBB', diff.index + diff.replace_count - 1)
                range_end = find_array_item(array, diff.index + diff.replace_count - 1)[1]

                value_c = to_c(diff.value)
                value_c = unwrap_braces(value_c)

                array = array[:range_start] + value_c + array[range_end:]

                c = c[:start] + array + c[end:]

            with open(f'{oot}/{diff.path}', 'wt') as f:
                f.write(c)

        elif isinstance(diff, ReplaceIncludes):
            log(f"Replace {len(diff.includes)} includes from {diff.first_index} in {diff.path}")

            with open(f'{oot}/{diff.path}', 'rt') as f:
                c = f.read()

            skip = diff.first_index
            includes = diff.includes[:]
            n = len(includes)
            done = 0
            log('---')
            log(c)
            log('---')

            def sub(m):
                log(m)
                log('=>', m.group(0))
                nonlocal skip
                nonlocal done
                if skip:
                    skip -= 1
                    return m.group(0)

                i = n - len(includes)
                name = diff.names[i]
                include = includes.pop(0)
                done += 1
                return f'u64 {name}[] = {{\n#include "{include}"\n}};'

            c = re.sub(
                r'^u64 .*?\] = \{\n#include.*?\n\};',
                sub,
                c,
                count=skip + len(includes),
                flags=re.MULTILINE
            )

            if done != n:
                raise Exception(f"Only managed to replace {done} of {n} includes.")

            with open(f'{oot}/{diff.path}', 'wt') as f:
                f.write(c)


        else:
            raise Exception()


def unwrap_braces(text):
    text = text.strip()
    assert text[0] == '{'
    assert text[-1] == '}'
    text = text[1:-1]
    return text
