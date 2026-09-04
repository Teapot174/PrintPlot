import sys
import os
import math
import random
import json
import re
from collections import defaultdict
import xml.etree.ElementTree as ET
import freetype
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout, QTextEdit, QCheckBox,
    QAbstractSpinBox, QSlider, QStyle, QStyleOptionSlider, QDialog
)
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer, QEvent
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPolygonF, QKeyEvent, QIcon


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class CleanDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)

    def keyPressEvent(self, event: QKeyEvent):
        if event.text() == '.':
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_Comma, event.modifiers(), ',')
        super().keyPressEvent(event)

    def valueFromText(self, text):
        suf = self.suffix()
        if suf:
            text = text.replace(suf, '')
        clean_text = text.replace(',', '.').replace(' ', '').strip()
        try:
            return float(clean_text)
        except ValueError:
            return self.minimum()

    def textFromValue(self, val):
        formatted = f"{val:.4f}".rstrip('0').rstrip('.')
        if not formatted or formatted == "-0":
            formatted = "0"
        return formatted.replace('.', ',')

    def fixup(self, text):
        return text.replace('.', ',')


class FontManager:
    def __init__(self):
        self.fonts = {}
        self.font_dirs = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            self.font_dirs.append(os.path.join(exe_dir, "fonts"))
            self.font_dirs.append(os.path.join(os.getcwd(), "fonts"))
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.font_dirs.append(os.path.join(script_dir, "fonts"))
            self.font_dirs.append(os.path.join(os.getcwd(), "fonts"))
        self.font_dirs = list(dict.fromkeys(self.font_dirs))
        if self.font_dirs:
            primary_dir = self.font_dirs[0]
            if not os.path.exists(primary_dir):
                try:
                    os.makedirs(primary_dir, exist_ok=True)
                except Exception:
                    pass
        self.scan_fonts()

    def scan_fonts(self):
        self.fonts = {}
        for font_dir in self.font_dirs:
            if os.path.exists(font_dir):
                for f in os.listdir(font_dir):
                    if f.lower().endswith(('.ttf', '.otf')):
                        path = os.path.join(font_dir, f)
                        try:
                            face = freetype.Face(path)
                            name = face.family_name.decode('utf-8', 'ignore')
                            self.fonts[name] = path
                        except Exception:
                            pass

    def get_path(self, font_name):
        return self.fonts.get(font_name)

    def get_names(self):
        return list(self.fonts.keys())


class SvgContourGenerator:
    def __init__(self):
        pass

    def parse_svg_file(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            contours = []
            for path_elem in root.iter('{http://www.w3.org/2000/svg}path'):
                d = path_elem.get('d')
                if not d:
                    continue
                contours.extend(self._parse_path(d))
            return contours
        except Exception as e:
            raise Exception(f"Ошибка при разборе SVG: {e}")

    def _parse_path(self, d):
        tokens = re.findall(r'[a-zA-Z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
        if not tokens:
            return []

        contours = []
        current_contour = []
        current_pos = (0.0, 0.0)
        start_pos = (0.0, 0.0)
        last_command = ''
        i = 0

        while i < len(tokens):
            token = tokens[i]
            if token.isalpha():
                cmd = token
                i += 1
            else:
                cmd = last_command
                if not cmd:
                    i += 1
                    continue

            if cmd in 'Mm':
                points = self._read_points(tokens, i, 2)
                if not points:
                    break
                if cmd == 'm':
                    x = current_pos[0] + points[0]
                    y = current_pos[1] + points[1]
                else:
                    x, y = points
                current_pos = (x, y)
                start_pos = current_pos
                if current_contour:
                    contours.append(current_contour)
                current_contour = [(x, y)]
                i += 2
                last_command = cmd
            elif cmd in 'Ll':
                points = self._read_points(tokens, i, 2)
                if not points:
                    break
                if cmd == 'l':
                    x = current_pos[0] + points[0]
                    y = current_pos[1] + points[1]
                else:
                    x, y = points
                current_contour.append((x, y))
                current_pos = (x, y)
                i += 2
                last_command = cmd
            elif cmd in 'Hh':
                points = self._read_points(tokens, i, 1)
                if not points:
                    break
                if cmd == 'h':
                    x = current_pos[0] + points[0]
                else:
                    x = points[0]
                current_contour.append((x, current_pos[1]))
                current_pos = (x, current_pos[1])
                i += 1
                last_command = cmd
            elif cmd in 'Vv':
                points = self._read_points(tokens, i, 1)
                if not points:
                    break
                if cmd == 'v':
                    y = current_pos[1] + points[0]
                else:
                    y = points[0]
                current_contour.append((current_pos[0], y))
                current_pos = (current_pos[0], y)
                i += 1
                last_command = cmd
            elif cmd in 'Cc':
                points = self._read_points(tokens, i, 6)
                if not points:
                    break
                if cmd == 'c':
                    p1 = (current_pos[0] + points[0], current_pos[1] + points[1])
                    p2 = (current_pos[0] + points[2], current_pos[1] + points[3])
                    p3 = (current_pos[0] + points[4], current_pos[1] + points[5])
                else:
                    p1 = (points[0], points[1])
                    p2 = (points[2], points[3])
                    p3 = (points[4], points[5])
                steps = 20
                for j in range(1, steps + 1):
                    t = j / steps
                    x = (1-t)**3 * current_pos[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * p3[0]
                    y = (1-t)**3 * current_pos[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * p3[1]
                    current_contour.append((x, y))
                current_pos = p3
                i += 6
                last_command = cmd
            elif cmd in 'Ss':
                points = self._read_points(tokens, i, 4)
                if not points:
                    break
                i += 4
                last_command = cmd
            elif cmd in 'Qq':
                points = self._read_points(tokens, i, 4)
                if not points:
                    break
                if cmd == 'q':
                    p1 = (current_pos[0] + points[0], current_pos[1] + points[1])
                    p2 = (current_pos[0] + points[2], current_pos[1] + points[3])
                else:
                    p1 = (points[0], points[1])
                    p2 = (points[2], points[3])
                steps = 20
                for j in range(1, steps + 1):
                    t = j / steps
                    x = (1-t)**2 * current_pos[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
                    y = (1-t)**2 * current_pos[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
                    current_contour.append((x, y))
                current_pos = p2
                i += 4
                last_command = cmd
            elif cmd in 'Tt':
                points = self._read_points(tokens, i, 2)
                if not points:
                    break
                i += 2
                last_command = cmd
            elif cmd in 'Aa':
                points = self._read_points(tokens, i, 7)
                if not points:
                    break
                i += 7
                last_command = cmd
            elif cmd in 'Zz':
                if current_contour and len(current_contour) > 1:
                    current_contour.append(start_pos)
                    contours.append(current_contour)
                current_contour = []
                current_pos = start_pos
                i += 0
                last_command = cmd
            else:
                i += 1

        if current_contour and len(current_contour) > 1:
            contours.append(current_contour)

        return contours

    def _read_points(self, tokens, start_idx, count):
        if start_idx + count > len(tokens):
            return None
        points = []
        for j in range(start_idx, start_idx + count):
            try:
                points.append(float(tokens[j]))
            except ValueError:
                return None
        return points


class TextContourGenerator:
    def __init__(self, field_w=178.0, field_h=220.0):
        self.FIELD_W = field_w
        self.FIELD_H = field_h
        self._face_cache = {}

    def _get_face(self, font_path):
        if font_path not in self._face_cache:
            self._face_cache[font_path] = freetype.Face(font_path)
        return self._face_cache[font_path]

    def generate(self, text, font_path, size_mm, letter_spacing_mm=0.0,
                 line_spacing_factor=1.2, mode="Обычный",
                 origin_x=5.0, origin_y=205.0, right_margin=0.0,
                 humanize_level=1.0, auto_wrap=False):
        if not text or not font_path:
            return []
        face = self._get_face(font_path)
        units_per_EM = face.units_per_EM
        scale = size_mm / units_per_EM
        if auto_wrap:
            max_line_w = max(10.0, self.FIELD_W - origin_x - right_margin)
            wrapped_lines = self._wrap_text(text, face, scale, max_line_w, letter_spacing_mm)
        else:
            wrapped_lines = text.split('\n')
        all_contours = []
        line_height = size_mm * line_spacing_factor
        pen_y = 0.0
        norm = humanize_level * (5.0 / 18.0)
        line_x_shift_range = 0.3 * norm
        for line in wrapped_lines:
            if (origin_y + pen_y) < 0:
                break
            pen_x = random.uniform(-line_x_shift_range, line_x_shift_range)
            for ch in line:
                face.load_char(ch, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
                glyph = face.glyph
                outline = glyph.outline
                if mode == "Жирный":
                    try:
                        outline.bold(int(units_per_EM * 0.03))
                    except Exception:
                        pass
                elif mode == "Тонкий":
                    try:
                        outline.bold(-int(units_per_EM * 0.015))
                    except Exception:
                        pass
                contours = self._decompose_outline(outline, scale)
                if mode == "Тонкий" and len(contours) > 1:
                    outer_contours = []
                    for i, c1 in enumerate(contours):
                        if not c1:
                            continue
                        is_inner = False
                        pt_x, pt_y = c1[0]
                        for j, c2 in enumerate(contours):
                            if i != j and len(c2) >= 3:
                                if self._point_in_polygon(pt_x, pt_y, c2):
                                    is_inner = True
                                    break
                        if not is_inner:
                            outer_contours.append(c1)
                    contours = outer_contours
                if contours and humanize_level > 0.0:
                    all_pts = [pt for c in contours for pt in c]
                    if all_pts:
                        min_x = min(pt[0] for pt in all_pts)
                        max_x = max(pt[0] for pt in all_pts)
                        min_y = min(pt[1] for pt in all_pts)
                        max_y = max(pt[1] for pt in all_pts)
                        cx = (min_x + max_x) / 2.0
                        cy = (min_y + max_y) / 2.0
                        angle_range = 3.0 * norm
                        scale_range = 0.05 * norm
                        shift_x_range = 0.3 * norm
                        shift_y_range = 0.4 * norm
                        angle_rad = math.radians(random.uniform(-angle_range, angle_range))
                        scale_x = random.uniform(1.0 - scale_range, 1.0 + scale_range)
                        scale_y = random.uniform(1.0 - scale_range, 1.0 + scale_range)
                        shift_x = random.uniform(-shift_x_range, shift_x_range)
                        shift_y = random.uniform(-shift_y_range, shift_y_range)
                        cos_a = math.cos(angle_rad)
                        sin_a = math.sin(angle_rad)
                        transformed = []
                        for c in contours:
                            tc = []
                            for x, y in c:
                                dx = (x - cx) * scale_x
                                dy = (y - cy) * scale_y
                                rx = dx * cos_a - dy * sin_a
                                ry = dx * sin_a + dy * cos_a
                                tc.append((cx + rx + shift_x, cy + ry + shift_y))
                            transformed.append(tc)
                        contours = transformed
                for contour in contours:
                    shifted = [(x + pen_x, y + pen_y) for x, y in contour]
                    all_contours.append(shifted)
                advance = glyph.metrics.horiAdvance * scale + letter_spacing_mm
                pen_x += advance
            pen_y -= line_height
        all_contours = self._deduplicate_and_chain(all_contours)
        clipped_contours = []
        for contour in all_contours:
            sub = []
            for x, y in contour:
                abs_x = x + origin_x
                abs_y = y + origin_y
                if 0.0 <= abs_x <= self.FIELD_W and 0.0 <= abs_y <= self.FIELD_H:
                    sub.append((x, y))
                else:
                    if len(sub) > 1:
                        clipped_contours.append(sub)
                    sub = []
            if len(sub) > 1:
                clipped_contours.append(sub)
        return clipped_contours

    def wrap_text_to_string(self, text, font_path, size_mm, letter_spacing_mm, max_line_w):
        face = self._get_face(font_path)
        units_per_EM = face.units_per_EM
        scale = size_mm / units_per_EM
        wrapped_lines = self._wrap_text(text, face, scale, max_line_w, letter_spacing_mm)
        return "\n".join(wrapped_lines)

    def _deduplicate_and_chain(self, contours):
        def key_pt(pt):
            return (round(pt[0], 2), round(pt[1], 2))
        unique_segments = {}
        for contour in contours:
            if len(contour) < 2:
                continue
            for i in range(len(contour) - 1):
                p1, p2 = contour[i], contour[i+1]
                k1, k2 = key_pt(p1), key_pt(p2)
                if k1 == k2:
                    continue
                seg_key = (k1, k2) if k1 < k2 else (k2, k1)
                if seg_key not in unique_segments:
                    unique_segments[seg_key] = (p1, p2, k1, k2)
        if not unique_segments:
            return []
        adj = defaultdict(list)
        for seg_key, (p1, p2, k1, k2) in unique_segments.items():
            adj[k1].append((k2, p1, p2, seg_key))
            adj[k2].append((k1, p2, p1, seg_key))
        visited_segs = set()
        new_contours = []
        for seg_key, (p1, p2, k1, k2) in list(unique_segments.items()):
            if seg_key in visited_segs:
                continue
            chain = [p1, p2]
            visited_segs.add(seg_key)
            curr = k2
            while True:
                next_item = None
                for nxt, pt1, pt2, skey in adj[curr]:
                    if skey not in visited_segs:
                        next_item = (nxt, pt1, pt2, skey)
                        break
                if not next_item:
                    break
                nxt, pt1, pt2, skey = next_item
                visited_segs.add(skey)
                chain.append(pt2)
                curr = nxt
            curr = k1
            while True:
                next_item = None
                for nxt, pt1, pt2, skey in adj[curr]:
                    if skey not in visited_segs:
                        next_item = (nxt, pt1, pt2, skey)
                        break
                if not next_item:
                    break
                nxt, pt1, pt2, skey = next_item
                visited_segs.add(skey)
                chain.insert(0, pt2)
                curr = nxt
            new_contours.append(chain)
        return new_contours

    def _point_in_polygon(self, x, y, poly):
        n = len(poly)
        inside = False
        p1x, p1y = poly[0]
        for i in range(n + 1):
            p2x, p2y = poly[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def _wrap_text(self, text, face, scale, max_width, letter_spacing):
        def char_w(c):
            face.load_char(c, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
            return face.glyph.metrics.horiAdvance * scale + letter_spacing
        def str_w(s):
            return sum(char_w(c) for c in s)
        space_w = char_w(' ')
        hyphen_w = char_w('-')
        final_lines = []
        paragraphs = text.split('\n')
        for para in paragraphs:
            words = para.split(' ')
            current_line = ""
            current_w = 0.0
            for word in words:
                w_width = str_w(word)
                needed = w_width if not current_line else (space_w + w_width)
                if current_w + needed <= max_width:
                    if current_line:
                        current_line += " " + word
                        current_w += space_w + w_width
                    else:
                        current_line = word
                        current_w = w_width
                else:
                    if current_line:
                        final_lines.append(current_line)
                        current_line = ""
                        current_w = 0.0
                    if str_w(word) <= max_width:
                        current_line = word
                        current_w = str_w(word)
                    else:
                        rem_word = word
                        while rem_word:
                            if str_w(rem_word) <= max_width:
                                current_line = rem_word
                                current_w = str_w(rem_word)
                                rem_word = ""
                            else:
                                sub = ""
                                sub_w = 0.0
                                split_idx = 0
                                for idx, ch in enumerate(rem_word):
                                    cw = char_w(ch)
                                    if sub_w + cw + hyphen_w > max_width:
                                        break
                                    sub += ch
                                    sub_w += cw
                                    split_idx = idx + 1
                                if split_idx == 0:
                                    split_idx = 1
                                    sub = rem_word[:1]
                                final_lines.append(sub + "-")
                                rem_word = rem_word[split_idx:]
                                current_line = ""
                                current_w = 0.0
            if current_line:
                final_lines.append(current_line)
        return final_lines

    def _decompose_outline(self, outline, scale):
        contours = []
        current_contour = []
        def move_to(a, ctx):
            nonlocal current_contour
            if current_contour:
                contours.append(current_contour)
            x = a.x * scale
            y = a.y * scale
            current_contour = [(x, y)]
        def line_to(a, ctx):
            nonlocal current_contour
            x = a.x * scale
            y = a.y * scale
            current_contour.append((x, y))
        def conic_to(a, b, ctx):
            nonlocal current_contour
            p0 = current_contour[-1]
            p1 = (a.x * scale, a.y * scale)
            p2 = (b.x * scale, b.y * scale)
            steps = 10
            for i in range(1, steps + 1):
                t = i / steps
                x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
                y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
                current_contour.append((x, y))
        def cubic_to(a, b, c, ctx):
            nonlocal current_contour
            p0 = current_contour[-1]
            p1 = (a.x * scale, a.y * scale)
            p2 = (b.x * scale, b.y * scale)
            p3 = (c.x * scale, c.y * scale)
            steps = 10
            for i in range(1, steps + 1):
                t = i / steps
                x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
                y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[1]
                current_contour.append((x, y))
        outline.decompose(
            move_to=move_to,
            line_to=line_to,
            conic_to=conic_to,
            cubic_to=cubic_to,
            shift=0,
            delta=0
        )
        if current_contour:
            contours.append(current_contour)
        return contours


class GCodeGenerator:
    def __init__(self, settings):
        self.settings = settings

    def _fmt(self, val):
        s = f"{val:.3f}".rstrip('0').rstrip('.')
        return s if s else "0"

    def generate(self, contours):
        s = self.settings
        lines = []
        lines.append("M220")
        lines.append("S100")
        lines.append("M221")
        lines.append("S100")
        lines.append("G90")
        lines.append("G28")
        lines.append("G1 Z10 F3000")
        lines.append(f"G1 X{self._fmt(s['nozzle_offset_x'])} Y{self._fmt(s['nozzle_offset_y'])} F15000")
        lines.append("G92 X0 Y0")
        lines.append("; Generated by PrintPlot")
        lines.append("G21 ; millimeters")
        approach_z = s.get('approach_z', 20.0)
        lines.append(f"G0 Z{self._fmt(approach_z)} F{self._fmt(s['travel_speed'] * 60)}")
        lines.append(f"G0 X0 Y0 F{self._fmt(s['travel_speed'] * 60)}")
        spine_z = s.get('spine_z_offset', 0.0)
        spine_length = s.get('spine_length', 5.0)
        origin_x = s.get('origin_x', 0.0)
        origin_y = s.get('origin_y', 0.0)
        def spine_offset(actual_x: float) -> float:
            if spine_z <= 0 or spine_length <= 0:
                return 0.0
            rel_x = actual_x - origin_x
            if rel_x <= 0:
                return spine_z
            elif rel_x >= spine_length:
                return 0.0
            else:
                return spine_z * (1.0 - rel_x / spine_length)
        safe_lift = max(s['z_lift'], spine_z)
        first_contour = True
        for contour in contours:
            if not contour:
                continue
            start_x = contour[0][0] + origin_x
            start_y = contour[0][1] + origin_y
            if first_contour:
                lines.append(f"G0 X{self._fmt(start_x)} Y{self._fmt(start_y)} F{self._fmt(s['travel_speed'] * 60)}")
                first_contour = False
            else:
                lines.append(f"G0 Z{self._fmt(safe_lift)} F{self._fmt(s['travel_speed'] * 60)}")
                lines.append(f"G0 X{self._fmt(start_x)} Y{self._fmt(start_y)} F{self._fmt(s['travel_speed'] * 60)}")
            z_start = s['z_work'] + spine_offset(start_x)
            lines.append(f"G1 Z{self._fmt(z_start)} F{self._fmt(s['plunge_speed'] * 60)}")
            lines.append("M3 S100")
            for i in range(1, len(contour)):
                x = contour[i][0] + origin_x
                y = contour[i][1] + origin_y
                z = s['z_work'] + spine_offset(x)
                lines.append(f"G1 X{self._fmt(x)} Y{self._fmt(y)} Z{self._fmt(z)} F{self._fmt(s['engrave_speed'] * 60)}")
            lines.append("M5")
            lines.append(f"G0 Z{self._fmt(safe_lift)} F{self._fmt(s['travel_speed'] * 60)}")
        lines.append(f"G0 Z{self._fmt(approach_z)} F{self._fmt(s['travel_speed'] * 60)}")
        lines.append("G0 X0 Y0 ; return to origin")
        lines.append("M5 ; ensure tool off")
        lines.append("M30 ; end of program")
        return "\n".join(lines)


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.contours = []
        self.field_size = (178.0, 220.0)
        self.display_size = (178.0, 220.0)
        self.origin = (0, 0)
        self.nozzle_offset = (48, 0)
        self.right_margin = 0.0
        self.grid_mode = "full"
        self.drag_enabled = False
        self.drag_callback = None
        self._drag_start_pos = None
        self._drag_start_origin = None
        self.setMinimumSize(500, 500)

    def set_data(self, contours, origin, nozzle_offset, right_margin=0.0, grid_mode="full", field_size=None):
        self.contours = contours
        self.origin = origin
        self.nozzle_offset = nozzle_offset
        self.right_margin = right_margin
        self.grid_mode = grid_mode
        if field_size:
            self.field_size = field_size
        if self.grid_mode in ("ruler", "cell_empty_top"):
            self.display_size = (160.0, 200.0)
        else:
            self.display_size = self.field_size
        self.update()

    def set_drag_enabled(self, enabled):
        self.drag_enabled = enabled
        if not enabled:
            self._drag_start_pos = None
            self._drag_start_origin = None

    def set_drag_callback(self, callback):
        self.drag_callback = callback

    def _get_field_geometry(self):
        margin = 20
        widget_w = self.width() - 2 * margin
        widget_h = self.height() - 2 * margin
        field_w, field_h = self.display_size
        scale = min(widget_w / field_w, widget_h / field_h)
        offset_x = (self.width() - field_w * scale) / 2
        offset_y = (self.height() - field_h * scale) / 2
        return scale, offset_x, offset_y

    def mousePressEvent(self, event):
        if self.drag_enabled and event.button() == Qt.LeftButton:
            self._drag_start_pos = (event.x(), event.y())
            self._drag_start_origin = self.origin
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_enabled and self._drag_start_pos is not None and (event.buttons() & Qt.LeftButton):
            scale, _, _ = self._get_field_geometry()
            start_x, start_y = self._drag_start_pos
            dx = (event.x() - start_x) / scale
            dy = -(event.y() - start_y) / scale
            new_origin_x = self._drag_start_origin[0] + dx
            new_origin_y = self._drag_start_origin[1] + dy
            if self.drag_callback:
                self.drag_callback(new_origin_x, new_origin_y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_enabled and event.button() == Qt.LeftButton and self._drag_start_pos is not None:
            self._drag_start_pos = None
            self._drag_start_origin = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#2b2b2b"))
        margin = 20
        widget_w = self.width() - 2 * margin
        widget_h = self.height() - 2 * margin
        field_w, field_h = self.display_size
        scale = min(widget_w / field_w, widget_h / field_h)
        offset_x = (self.width() - field_w * scale) / 2
        offset_y = (self.height() - field_h * scale) / 2
        pen = QPen(QColor("#6ef0d4"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(QRectF(offset_x, offset_y, field_w * scale, field_h * scale))
        if self.grid_mode == "ruler":
            step = 8.0
            shift = 0.0
            pen = QPen(QColor("#777777"))
            pen.setWidth(1)
            painter.setPen(pen)
            y_virt = shift + step
            while y_virt < field_h - step:
                y_pix = offset_y + (field_h - y_virt) * scale
                painter.drawLine(int(offset_x), int(y_pix), int(offset_x + field_w * scale), int(y_pix))
                y_virt += step
        elif self.grid_mode == "cell":
            step = 5.0
            pen = QPen(QColor("#777777"))
            pen.setWidth(1)
            painter.setPen(pen)
            for x in range(0, int(field_w) + 1, int(step)):
                x_pix = offset_x + x * scale
                painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
            for y in range(0, int(field_h) + 1, int(step)):
                y_pix = offset_y + (field_h - y) * scale
                painter.drawLine(int(offset_x), int(y_pix), int(offset_x + field_w * scale), int(y_pix))
        elif self.grid_mode == "cell_empty_top":
            step = 5.0
            shift = 1.0
            pen = QPen(QColor("#777777"))
            pen.setWidth(1)
            painter.setPen(pen)
            for x in range(0, int(field_w) + 1, int(step)):
                x_pix = offset_x + x * scale
                painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
            y_virt = shift
            while y_virt <= field_h:
                y_pix = offset_y + (field_h - y_virt) * scale
                painter.drawLine(int(offset_x), int(y_pix), int(offset_x + field_w * scale), int(y_pix))
                y_virt += step
        else:
            pen = QPen(QColor("#777777"))
            pen.setWidth(1)
            painter.setPen(pen)
            for x in range(0, int(field_w) + 1, 10):
                x_pix = offset_x + x * scale
                painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
            for y in range(0, int(field_h) + 1, 10):
                y_pix = offset_y + (field_h - y) * scale
                painter.drawLine(int(offset_x), int(y_pix), int(offset_x + field_w * scale), int(y_pix))
            pen = QPen(QColor("#3a3a3a"))
            pen.setWidth(0)
            painter.setPen(pen)
            for x in range(0, int(field_w) + 1):
                if x % 10 != 0:
                    x_pix = offset_x + x * scale
                    painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
            for y in range(0, int(field_h) + 1):
                if y % 10 != 0:
                    y_pix = offset_y + (field_h - y) * scale
                    painter.drawLine(int(offset_x), int(y_pix), int(offset_x + field_w * scale), int(y_pix))
        if self.right_margin > 0:
            pen = QPen(QColor("#ff2020"))
            pen.setWidth(2)
            painter.setPen(pen)
            if self.grid_mode in ("ruler", "cell_empty_top"):
                margin_field_w = self.display_size[0]
                x_real = margin_field_w - self.right_margin
                if x_real >= 0:
                    x_pix = offset_x + x_real * scale
                    painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
            else:
                x_real = field_w - self.right_margin
                if x_real >= 0:
                    x_pix = offset_x + x_real * scale
                    painter.drawLine(int(x_pix), int(offset_y), int(x_pix), int(offset_y + field_h * scale))
        if self.contours:
            pen = QPen(QColor("#ffffff"))
            pen.setWidth(1)
            painter.setPen(pen)
            for contour in self.contours:
                if not contour:
                    continue
                poly = QPolygonF()
                for x, y in contour:
                    display_x = x + self.origin[0]
                    display_y = y + self.origin[1]
                    pix_x = offset_x + display_x * scale
                    pix_y = offset_y + (field_h - display_y) * scale
                    poly.append(QPointF(pix_x, pix_y))
                if poly.size() > 1:
                    painter.drawPolyline(poly)


class SnapSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            handle_rect = self.style().subControlRect(
                QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
            )
            if not handle_rect.contains(event.pos()):
                groove_rect = self.style().subControlRect(
                    QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
                )
                if groove_rect.width() > 0:
                    value = QStyle.sliderValueFromPosition(
                        self.minimum(), self.maximum(),
                        event.x() - groove_rect.x(),
                        groove_rect.width(),
                        self.invertedAppearance()
                    )
                    value = int(round(value))
                    value = max(self.minimum(), min(self.maximum(), value))
                    self.setSliderPosition(value)
                    self._dragging = True
                    self.setSliderDown(True)
                    self.sliderPressed.emit()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            groove_rect = self.style().subControlRect(
                QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self
            )
            if groove_rect.width() > 0:
                value = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    event.x() - groove_rect.x(),
                    groove_rect.width(),
                    self.invertedAppearance()
                )
                value = int(round(value))
                value = max(self.minimum(), min(self.maximum(), value))
                self.setSliderPosition(value)
                self.sliderMoved.emit(value)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PrinterSettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(350)
        self.settings = settings or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.field_w_spin = CleanDoubleSpinBox()
        self.field_w_spin.setRange(100, 420)
        self.field_w_spin.setDecimals(1)
        self.field_w_spin.setValue(self.settings.get('field_w', 220.0))
        self.field_w_spin.setSuffix(" мм")
        form.addRow("Ширина поля:", self.field_w_spin)
        self.field_h_spin = CleanDoubleSpinBox()
        self.field_h_spin.setRange(100, 420)
        self.field_h_spin.setDecimals(1)
        self.field_h_spin.setValue(self.settings.get('field_h', 220.0))
        self.field_h_spin.setSuffix(" мм")
        form.addRow("Высота поля:", self.field_h_spin)
        self.nozzle_x_spin = CleanDoubleSpinBox()
        self.nozzle_x_spin.setRange(-500, 500)
        self.nozzle_x_spin.setDecimals(1)
        self.nozzle_x_spin.setValue(self.settings.get('nozzle_offset_x', 0.0))
        self.nozzle_x_spin.setSuffix(" мм")
        form.addRow("Смещение сопла X:", self.nozzle_x_spin)
        self.nozzle_y_spin = CleanDoubleSpinBox()
        self.nozzle_y_spin.setRange(-500, 500)
        self.nozzle_y_spin.setDecimals(1)
        self.nozzle_y_spin.setValue(self.settings.get('nozzle_offset_y', 0.0))
        self.nozzle_y_spin.setSuffix(" мм")
        form.addRow("Смещение сопла Y:", self.nozzle_y_spin)
        self.travel_spin = CleanDoubleSpinBox()
        self.travel_spin.setRange(1, 1000)
        self.travel_spin.setDecimals(0)
        self.travel_spin.setValue(self.settings.get('travel_speed', 200))
        self.travel_spin.setSuffix(" мм/с")
        form.addRow("Скорость перемещения:", self.travel_spin)
        self.engrave_spin = CleanDoubleSpinBox()
        self.engrave_spin.setRange(1, 1000)
        self.engrave_spin.setDecimals(0)
        self.engrave_spin.setValue(self.settings.get('engrave_speed', 200))
        self.engrave_spin.setSuffix(" мм/с")
        form.addRow("Скорость рисования:", self.engrave_spin)
        self.plunge_spin = CleanDoubleSpinBox()
        self.plunge_spin.setRange(1, 100)
        self.plunge_spin.setDecimals(0)
        self.plunge_spin.setValue(self.settings.get('plunge_speed', 10))
        self.plunge_spin.setSuffix(" мм/с")
        form.addRow("Скорость Z:", self.plunge_spin)
        layout.addLayout(form)
        btn_layout = QHBoxLayout()
        export_btn = QPushButton("Экспорт конфига")
        export_btn.clicked.connect(self.export_config)
        import_btn = QPushButton("Импорт конфига")
        import_btn.clicked.connect(self.import_config)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(import_btn)
        layout.addLayout(btn_layout)
        btn_layout2 = QHBoxLayout()
        reset_btn = QPushButton("Сбросить всё")
        reset_btn.clicked.connect(self.reset_defaults)
        ok_btn = QPushButton("Применить")
        ok_btn.clicked.connect(self.accept)
        btn_layout2.addWidget(reset_btn)
        btn_layout2.addWidget(ok_btn)
        layout.addLayout(btn_layout2)

        for btn in (export_btn, import_btn, reset_btn, ok_btn):
            btn.setAutoDefault(False)
        ok_btn.setDefault(False)

        self.setFixedSize(380, 380)

    def get_settings(self):
        return {
            'field_w': self.field_w_spin.value(),
            'field_h': self.field_h_spin.value(),
            'nozzle_offset_x': self.nozzle_x_spin.value(),
            'nozzle_offset_y': self.nozzle_y_spin.value(),
            'travel_speed': self.travel_spin.value(),
            'plunge_speed': self.plunge_spin.value(),
            'engrave_speed': self.engrave_spin.value()
        }

    def reset_defaults(self):
        self.field_w_spin.setValue(220.0)
        self.field_h_spin.setValue(220.0)
        self.nozzle_x_spin.setValue(0.0)
        self.nozzle_y_spin.setValue(0.0)
        self.travel_spin.setValue(200)
        self.plunge_spin.setValue(10)
        self.engrave_spin.setValue(200)

    def export_config(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Экспорт", "", "JSON files (*.json)")
        if file_path:
            data = self.get_settings()
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")

    def import_config(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Импорт", "", "JSON files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.field_w_spin.setValue(data.get('field_w', 220.0))
                self.field_h_spin.setValue(data.get('field_h', 220.0))
                self.nozzle_x_spin.setValue(data.get('nozzle_offset_x', 0.0))
                self.nozzle_y_spin.setValue(data.get('nozzle_offset_y', 0.0))
                self.travel_spin.setValue(data.get('travel_speed', 200))
                self.plunge_spin.setValue(data.get('plunge_speed', 10))
                self.engrave_spin.setValue(data.get('engrave_speed', 200))
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить: {e}")
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PrintPlot v1.1 | by Teapot174")
        self.setWindowIcon(QIcon(resource_path("logo.png")))
        self.setGeometry(100, 100, 1100, 770)
        self.font_manager = FontManager()
        self.contour_gen = TextContourGenerator()
        self.svg_gen = SvgContourGenerator()
        self.contours = []
        self.field_w = 220.0
        self.field_h = 220.0
        self.nozzle_offset_x = 0.0
        self.nozzle_offset_y = 0.0
        self.travel_speed = 200.0
        self.plunge_speed = 10.0
        self.engrave_speed = 200.0
        self.is_image_mode = False
        self.svg_raw_contours = []
        self.image_scale = 1.0
        self.image_offset_x = 0.0
        self.image_offset_y = 0.0
        self.image_rotation = 0.0
        self.hatch_level = 0
        self.hatch_angle = 45
        self.invert_image = False
        self.load_printer_settings()
        self.save_printer_settings()
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(400)
        self.debounce_timer.timeout.connect(self.on_param_changed)
        self.image_update_timer = QTimer()
        self.image_update_timer.setSingleShot(True)
        self.image_update_timer.setInterval(50)
        self.image_update_timer.timeout.connect(self.update_image_transforms)
        self.init_ui()
        self.update_font_list()
        self.apply_preset("Свободный")
        self.apply_auto_wrap()

    def load_printer_settings(self):
        config_path = self.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.field_w = max(100.0, data.get('field_w', 220.0))
                self.field_h = max(100.0, data.get('field_h', 220.0))
                self.nozzle_offset_x = data.get('nozzle_offset_x', 0.0)
                self.nozzle_offset_y = data.get('nozzle_offset_y', 0.0)
                self.travel_speed = data.get('travel_speed', 200.0)
                self.plunge_speed = data.get('plunge_speed', 10.0)
                self.engrave_speed = data.get('engrave_speed', 200.0)
            except Exception:
                pass

    def save_printer_settings(self):
        config_path = self.get_config_path()
        data = {
            'field_w': self.field_w,
            'field_h': self.field_h,
            'nozzle_offset_x': self.nozzle_offset_x,
            'nozzle_offset_y': self.nozzle_offset_y,
            'travel_speed': self.travel_speed,
            'plunge_speed': self.plunge_speed,
            'engrave_speed': self.engrave_speed
        }
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def get_config_path(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "printplot.json")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(15)
        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)

        self.text_group = QGroupBox("Шрифт")
        font_form = QFormLayout()
        self.font_combo = QComboBox()
        font_form.addRow("Шрифт:", self.font_combo)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Обычный", "Тонкий", "Жирный"])
        font_form.addRow("Режим начертания:", self.mode_combo)
        self.font_size_spin = CleanDoubleSpinBox()
        self.font_size_spin.setRange(1, 100)
        self.font_size_spin.setDecimals(1)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setSuffix(" мм")
        font_form.addRow("Высота шрифта:", self.font_size_spin)
        self.letter_spacing_spin = CleanDoubleSpinBox()
        self.letter_spacing_spin.setRange(-10, 20)
        self.letter_spacing_spin.setDecimals(1)
        self.letter_spacing_spin.setValue(0.0)
        self.letter_spacing_spin.setSuffix(" мм")
        font_form.addRow("Межбукв. интервал:", self.letter_spacing_spin)
        self.line_spacing_spin = CleanDoubleSpinBox()
        self.line_spacing_spin.setRange(0.1, 3.0)
        self.line_spacing_spin.setSingleStep(0.1)
        self.line_spacing_spin.setDecimals(1)
        self.line_spacing_spin.setValue(1.2)
        font_form.addRow("Межстрочный интервал:", self.line_spacing_spin)
        self.humanize_title_label = QLabel("Humanize: 0")
        self.humanize_slider = SnapSlider(Qt.Horizontal)
        self.humanize_slider.setRange(0, 8)
        self.humanize_slider.setValue(0)
        self.humanize_slider.setTickPosition(QSlider.TicksBelow)
        self.humanize_slider.setTickInterval(1)
        self.humanize_slider.setFocusPolicy(Qt.NoFocus)
        self.humanize_slider.setPageStep(1)
        self.humanize_slider.valueChanged.connect(self.on_humanize_changed)
        humanize_widget = QWidget()
        humanize_widget.setStyleSheet("background: transparent;")
        humanize_layout = QHBoxLayout(humanize_widget)
        humanize_layout.setContentsMargins(0, 0, 0, 0)
        humanize_layout.addWidget(self.humanize_slider)
        font_form.addRow(self.humanize_title_label, humanize_widget)
        self.text_group.setLayout(font_form)
        left_panel.addWidget(self.text_group)

        self.image_group = QGroupBox("Изображение")
        image_layout = QVBoxLayout()
        self.load_svg_btn = QPushButton("Загрузить SVG")
        self.load_svg_btn.clicked.connect(self.load_svg_file)
        image_layout.addWidget(self.load_svg_btn)
        self.svg_filename_label = QLabel("Файл не выбран")
        self.svg_filename_label.setWordWrap(True)
        image_layout.addWidget(self.svg_filename_label)

        scale_widget = QWidget()
        scale_widget.setStyleSheet("background: transparent;")
        scale_layout = QHBoxLayout(scale_widget)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.addWidget(QLabel("Масштаб:"))
        self.image_scale_slider = QSlider(Qt.Horizontal)
        self.image_scale_slider.setRange(1, 100000)
        self.image_scale_slider.setValue(10000)
        self.image_scale_slider.setFocusPolicy(Qt.NoFocus)
        self.image_scale_slider.setPageStep(1000)
        self.image_scale_slider.valueChanged.connect(self.on_image_scale_slider_changed)
        scale_layout.addWidget(self.image_scale_slider)
        self.image_scale_spin = CleanDoubleSpinBox()
        self.image_scale_spin.setRange(0.0001, 10.0)
        self.image_scale_spin.setDecimals(4)
        self.image_scale_spin.setSingleStep(0.0001)
        self.image_scale_spin.setValue(1.0)
        self.image_scale_spin.setSuffix(" x")
        self.image_scale_spin.valueChanged.connect(self.on_image_scale_spin_changed)
        scale_layout.addWidget(self.image_scale_spin)
        image_layout.addWidget(scale_widget)

        self.rotation_title_label = QLabel("Поворот: 0°")
        self.rotation_slider = SnapSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setTickPosition(QSlider.TicksBelow)
        self.rotation_slider.setTickInterval(30)
        self.rotation_slider.setFocusPolicy(Qt.NoFocus)
        self.rotation_slider.setPageStep(10)
        self.rotation_slider.valueChanged.connect(self.on_rotation_changed)
        rotation_widget = QWidget()
        rotation_widget.setStyleSheet("background: transparent;")
        rotation_layout = QHBoxLayout(rotation_widget)
        rotation_layout.setContentsMargins(0, 0, 0, 0)
        rotation_layout.addWidget(self.rotation_slider)
        image_layout.addWidget(self.rotation_title_label)
        image_layout.addWidget(rotation_widget)

        self.hatch_angle_combo = QComboBox()
        self.hatch_angle_combo.addItems(["Диагональ ↗", "Диагональ ↘", "Горизонтальная", "Вертикальная"])
        self.hatch_angle_combo.setCurrentIndex(0)
        self.hatch_angle_combo.currentIndexChanged.connect(self.on_hatch_angle_changed)
        image_layout.addWidget(QLabel("Направление штриховки:"))
        image_layout.addWidget(self.hatch_angle_combo)

        self.hatch_title_label = QLabel("Штриховка: 0")
        self.hatch_slider = SnapSlider(Qt.Horizontal)
        self.hatch_slider.setRange(0, 10)
        self.hatch_slider.setValue(0)
        self.hatch_slider.setTickPosition(QSlider.TicksBelow)
        self.hatch_slider.setTickInterval(1)
        self.hatch_slider.setFocusPolicy(Qt.NoFocus)
        self.hatch_slider.setPageStep(1)
        self.hatch_slider.valueChanged.connect(self.on_hatch_changed)
        hatch_widget = QWidget()
        hatch_widget.setStyleSheet("background: transparent;")
        hatch_layout = QHBoxLayout(hatch_widget)
        hatch_layout.setContentsMargins(0, 0, 0, 0)
        hatch_layout.addWidget(self.hatch_slider)
        image_layout.addWidget(self.hatch_title_label)
        image_layout.addWidget(hatch_widget)

        self.invert_button = QPushButton("Отразить зеркально")
        self.invert_button.clicked.connect(self.on_invert_clicked)
        image_layout.addWidget(self.invert_button)

        self.image_group.setLayout(image_layout)
        self.image_group.setVisible(False)
        left_panel.addWidget(self.image_group)

        position_group = QGroupBox("Позиция")
        pos_layout = QFormLayout()
        self.origin_x_spin = CleanDoubleSpinBox()
        self.origin_x_spin.setRange(-1000, 1000)
        self.origin_x_spin.setDecimals(1)
        self.origin_x_spin.setValue(5)
        self.origin_x_spin.setSuffix(" мм")
        pos_layout.addRow("Начало X:", self.origin_x_spin)
        self.origin_y_spin = CleanDoubleSpinBox()
        self.origin_y_spin.setRange(-1000, 1000)
        self.origin_y_spin.setDecimals(1)
        self.origin_y_spin.setValue(self.field_h - 10)
        self.origin_y_spin.setSuffix(" мм")
        pos_layout.addRow("Начало Y:", self.origin_y_spin)
        self.right_margin_spin = CleanDoubleSpinBox()
        self.right_margin_spin.setRange(0, 50)
        self.right_margin_spin.setDecimals(1)
        self.right_margin_spin.setValue(0.0)
        self.right_margin_spin.setSuffix(" мм")
        pos_layout.addRow("Отступ справа:", self.right_margin_spin)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["Свободный", "Линейная тетрадь", "Клеточная тетрадь", "Изображение"])
        self.preset_combo.activated.connect(lambda: self.apply_preset(self.preset_combo.currentText()))
        pos_layout.addRow("Режим:", self.preset_combo)
        position_group.setLayout(pos_layout)
        left_panel.addWidget(position_group)

        gcode_group = QGroupBox("Настройка GCODE")
        gcode_layout = QFormLayout()
        self.z_lift_label = QLabel("Высота над буквами:")
        self.z_lift_spin = CleanDoubleSpinBox()
        self.z_lift_spin.setRange(0, 200)
        self.z_lift_spin.setDecimals(1)
        self.z_lift_spin.setValue(1.5)
        self.z_lift_spin.setSuffix(" мм")
        gcode_layout.addRow(self.z_lift_label, self.z_lift_spin)
        self.approach_z_spin = CleanDoubleSpinBox()
        self.approach_z_spin.setRange(0, 200)
        self.approach_z_spin.setDecimals(1)
        self.approach_z_spin.setValue(10.0)
        self.approach_z_spin.setSuffix(" мм")
        gcode_layout.addRow("Высота подхода:", self.approach_z_spin)
        self.z_work_spin = CleanDoubleSpinBox()
        self.z_work_spin.setRange(-10, 200)
        self.z_work_spin.setDecimals(1)
        self.z_work_spin.setValue(0.2)
        self.z_work_spin.setSuffix(" мм")
        gcode_layout.addRow("Рабочая высота:", self.z_work_spin)
        self.spine_z_spin = CleanDoubleSpinBox()
        self.spine_z_spin.setRange(0, 200)
        self.spine_z_spin.setDecimals(1)
        self.spine_z_spin.setValue(0.0)
        self.spine_z_spin.setSuffix(" мм")
        gcode_layout.addRow("Высота корешка:", self.spine_z_spin)
        self.spine_length_spin = CleanDoubleSpinBox()
        self.spine_length_spin.setRange(0.1, 200)
        self.spine_length_spin.setDecimals(1)
        self.spine_length_spin.setValue(10.0)
        self.spine_length_spin.setSuffix(" мм")
        gcode_layout.addRow("Длина корешка:", self.spine_length_spin)
        gcode_group.setLayout(gcode_layout)
        left_panel.addWidget(gcode_group)

        left_panel.addStretch()

        button_layout1 = QHBoxLayout()
        self.printer_btn = QPushButton("Настройки")
        self.printer_btn.setFixedHeight(40)
        self.printer_btn.clicked.connect(self.open_printer_settings)
        self.wrap_btn = QPushButton("Перенос строк")
        self.wrap_btn.setFixedHeight(40)
        self.wrap_btn.clicked.connect(self.apply_auto_wrap)
        button_layout1.addWidget(self.printer_btn)
        button_layout1.addWidget(self.wrap_btn)
        left_panel.addLayout(button_layout1)

        self.generate_btn = QPushButton("Сгенерировать GCODE")
        self.generate_btn.setFixedHeight(50)
        self.generate_btn.clicked.connect(self.generate_and_save_gcode)
        left_panel.addWidget(self.generate_btn)

        right_panel = QVBoxLayout()
        self.preview = PreviewWidget()
        self.preview.set_drag_callback(self.on_image_drag)
        right_panel.addWidget(self.preview, stretch=2)
        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setPlainText("Просто текст...")
        self.text_input.setPlaceholderText("Введите текст...")
        right_panel.addWidget(self.text_input, stretch=1)

        main_layout.addLayout(left_panel, stretch=2)
        main_layout.addLayout(right_panel, stretch=3)

        self.text_input.textChanged.connect(self.trigger_update)
        self.font_combo.currentIndexChanged.connect(self.trigger_update)
        self.mode_combo.currentIndexChanged.connect(self.trigger_update)
        self.font_size_spin.valueChanged.connect(self.trigger_update)
        self.letter_spacing_spin.valueChanged.connect(self.trigger_update)
        self.line_spacing_spin.valueChanged.connect(self.trigger_update)
        self.origin_x_spin.valueChanged.connect(self.on_origin_spin_changed)
        self.origin_y_spin.valueChanged.connect(self.on_origin_spin_changed)
        self.right_margin_spin.valueChanged.connect(self.trigger_update)

    def on_humanize_changed(self, value):
        self.humanize_title_label.setText(f"Humanize: {value}")
        self.trigger_update()

    def snap_to_common_angles(self, value):
        common = [0, 45, 90, 135, 180, 225, 270, 315, 360]
        for a in common:
            if abs(value - a) <= 2:
                return a
        return value

    def on_rotation_changed(self, value):
        snapped = self.snap_to_common_angles(value)
        if snapped != value:
            self.rotation_slider.blockSignals(True)
            self.rotation_slider.setValue(int(snapped))
            self.rotation_slider.blockSignals(False)
            value = snapped
        self.image_rotation = value
        self.rotation_title_label.setText(f"Поворот: {value}°")
        self.image_update_timer.start()

    def on_image_scale_slider_changed(self, value):
        scale = value * 0.0001
        self.image_scale = scale
        self.image_scale_spin.blockSignals(True)
        self.image_scale_spin.setValue(scale)
        self.image_scale_spin.blockSignals(False)
        self.image_update_timer.start()

    def on_image_scale_spin_changed(self, value):
        self.image_scale = value
        slider_val = int(round(value / 0.0001))
        self.image_scale_slider.blockSignals(True)
        self.image_scale_slider.setValue(slider_val)
        self.image_scale_slider.blockSignals(False)
        self.image_update_timer.start()

    def on_hatch_angle_changed(self):
        idx = self.hatch_angle_combo.currentIndex()
        if idx == 0:
            self.hatch_angle = 45
        elif idx == 1:
            self.hatch_angle = -45
        elif idx == 2:
            self.hatch_angle = 0
        else:
            self.hatch_angle = 90
        self.image_update_timer.start()

    def on_hatch_changed(self, value):
        self.hatch_level = value
        self.hatch_title_label.setText(f"Штриховка: {value}")
        self.image_update_timer.start()

    def on_invert_clicked(self):
        self.invert_image = not self.invert_image
        self.image_update_timer.start()

    def on_origin_spin_changed(self):
        if self.is_image_mode:
            self.image_offset_x = self.origin_x_spin.value()
            self.image_offset_y = self.origin_y_spin.value()
            self.update_image_origin_only()
        else:
            self.trigger_update()

    def on_image_drag(self, new_x, new_y):
        self.image_offset_x = new_x
        self.image_offset_y = new_y
        self.origin_x_spin.blockSignals(True)
        self.origin_y_spin.blockSignals(True)
        self.origin_x_spin.setValue(new_x)
        self.origin_y_spin.setValue(new_y)
        self.origin_x_spin.blockSignals(False)
        self.origin_y_spin.blockSignals(False)
        self.update_image_origin_only()

    def get_hatch_step(self):
        if self.hatch_level <= 0:
            return 0.0
        return 2.0 - (self.hatch_level - 1) * (1.0 / 9)

    def generate_horizontal_hatching(self, contours, step_mm):
        hatch_contours = []
        for contour in contours:
            if len(contour) < 3:
                continue
            if contour[0] != contour[-1]:
                contour_closed = contour + [contour[0]]
            else:
                contour_closed = contour
            min_y = min(p[1] for p in contour_closed)
            max_y = max(p[1] for p in contour_closed)
            y = min_y + step_mm * 0.5
            while y <= max_y:
                intersections = []
                for i in range(len(contour_closed) - 1):
                    x1, y1 = contour_closed[i]
                    x2, y2 = contour_closed[i+1]
                    if (y1 <= y < y2) or (y2 <= y < y1):
                        if y2 != y1:
                            x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                            intersections.append(x)
                intersections.sort()
                for i in range(0, len(intersections) - 1, 2):
                    if i+1 < len(intersections):
                        hatch_contours.append([(intersections[i], y), (intersections[i+1], y)])
                y += step_mm
        return hatch_contours

    def generate_hatching(self, contours, step_mm, angle_deg):
        if step_mm <= 0:
            return []
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(-angle_rad)
        sin_a = math.sin(-angle_rad)
        all_pts = [pt for c in contours for pt in c]
        if not all_pts:
            return []
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2

        rotated_contours = []
        for contour in contours:
            rot = []
            for x, y in contour:
                dx = x - cx
                dy = y - cy
                x_rot = dx * cos_a - dy * sin_a + cx
                y_rot = dx * sin_a + dy * cos_a + cy
                rot.append((x_rot, y_rot))
            rotated_contours.append(rot)

        hatch_rotated = self.generate_horizontal_hatching(rotated_contours, step_mm)

        angle_back = math.radians(angle_deg)
        cos_b = math.cos(angle_back)
        sin_b = math.sin(angle_back)
        hatch_final = []
        for line in hatch_rotated:
            new_line = []
            for x, y in line:
                dx = x - cx
                dy = y - cy
                x_fin = dx * cos_b - dy * sin_b + cx
                y_fin = dx * sin_b + dy * cos_b + cy
                new_line.append((x_fin, y_fin))
            hatch_final.append(new_line)

        seen = set()
        unique_hatch = []
        for line in hatch_final:
            p1 = (round(line[0][0], 2), round(line[0][1], 2))
            p2 = (round(line[1][0], 2), round(line[1][1], 2))
            key = (p1, p2) if p1 < p2 else (p2, p1)
            if key not in seen:
                seen.add(key)
                unique_hatch.append(line)
        return unique_hatch

    def update_image_transforms(self):
        if not self.svg_raw_contours:
            self.contours = []
            self.preview.set_data([], (0,0), (self.nozzle_offset_x, self.nozzle_offset_y), 0, "cell")
            return
        scaled = []
        for contour in self.svg_raw_contours:
            sc = [(x * self.image_scale, y * self.image_scale) for x, y in contour]
            scaled.append(sc)

        if self.invert_image:
            all_pts = [pt for c in scaled for pt in c]
            if all_pts:
                min_x = min(p[0] for p in all_pts)
                max_x = max(p[0] for p in all_pts)
                cx = (min_x + max_x) / 2
                scaled = [[(2*cx - x, y) for x, y in contour] for contour in scaled]

        if self.image_rotation != 0:
            all_pts = [pt for c in scaled for pt in c]
            if all_pts:
                min_x = min(p[0] for p in all_pts)
                max_x = max(p[0] for p in all_pts)
                min_y = min(p[1] for p in all_pts)
                max_y = max(p[1] for p in all_pts)
                cx = (min_x + max_x) / 2
                cy = (min_y + max_y) / 2
                angle_rad = math.radians(self.image_rotation)
                cos_a = math.cos(angle_rad)
                sin_a = math.sin(angle_rad)
                rotated = []
                for contour in scaled:
                    rot = []
                    for x, y in contour:
                        dx = x - cx
                        dy = y - cy
                        x_r = dx * cos_a - dy * sin_a + cx
                        y_r = dx * sin_a + dy * cos_a + cy
                        rot.append((x_r, y_r))
                    rotated.append(rot)
                scaled = rotated

        fill_contours = []
        for contour in scaled:
            if len(contour) >= 3:
                if abs(contour[0][0] - contour[-1][0]) < 0.01 and abs(contour[0][1] - contour[-1][1]) < 0.01:
                    min_x = min(p[0] for p in contour)
                    max_x = max(p[0] for p in contour)
                    min_y = min(p[1] for p in contour)
                    max_y = max(p[1] for p in contour)
                    if (max_x - min_x) >= 1.5 and (max_y - min_y) >= 1.5:
                        fill_contours.append(contour)

        if self.hatch_level > 0 and fill_contours:
            step = self.get_hatch_step()
            hatch = self.generate_hatching(fill_contours, step, self.hatch_angle)
            scaled.extend(hatch)

        self.contours = scaled
        self.preview.set_data(
            self.contours,
            (self.image_offset_x, self.image_offset_y),
            (self.nozzle_offset_x, self.nozzle_offset_y),
            right_margin=0, grid_mode="cell",
            field_size=(self.field_w, self.field_h)
        )

    def update_image_origin_only(self):
        self.preview.origin = (self.image_offset_x, self.image_offset_y)
        self.preview.update()

    def _reset_to_default(self):
        self.font_size_spin.setValue(12)
        self.letter_spacing_spin.setValue(0.0)
        self.line_spacing_spin.setValue(1.2)
        self.humanize_slider.setValue(0)
        self.origin_x_spin.setValue(5)
        self.right_margin_spin.setValue(0.0)
        self.z_lift_spin.setValue(1.5)
        self.approach_z_spin.setValue(15.0)
        self.preview.grid_mode = "cell"
        self.preview.set_drag_enabled(False)

    def clear_image(self):
        self.svg_raw_contours = []
        self.contours = []
        self.svg_filename_label.setText("Файл не выбран")
        self.image_scale_slider.setValue(10000)
        self.image_scale_spin.setValue(1.0)
        self.image_scale = 1.0
        self.rotation_slider.setValue(0)
        self.hatch_slider.setValue(0)
        self.hatch_angle_combo.setCurrentIndex(0)
        self.hatch_angle = 45
        self.invert_image = False
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.preview.set_drag_enabled(False)

    def reset_window_size(self):
        self.setGeometry(100, 100, 1100, 770)

    def apply_preset(self, preset_name):
        self._reset_to_default()
        if preset_name == "Изображение":
            self.is_image_mode = True
            self.text_group.setVisible(False)
            self.image_group.setVisible(True)
            self.text_input.setVisible(False)
            self.origin_x_spin.setRange(-1000, 1000)
            self.origin_y_spin.setRange(-1000, 1000)
            self.z_lift_label.setText("Высота над рисунком:")
            self.wrap_btn.setVisible(False)
            self.origin_x_spin.setValue(0)
            self.origin_y_spin.setValue(0)
            self.image_offset_x = 0
            self.image_offset_y = 0
            self.preview.set_drag_enabled(bool(self.svg_raw_contours))
            if self.svg_raw_contours:
                self.update_image_transforms()
            else:
                self.contours = []
                self.preview.set_data([], (0,0), (self.nozzle_offset_x, self.nozzle_offset_y), 0, "cell")
        else:
            if self.is_image_mode:
                self.clear_image()
            self.is_image_mode = False
            self.text_group.setVisible(True)
            self.image_group.setVisible(False)
            self.text_input.setVisible(True)
            self.preview.set_drag_enabled(False)
            self.reset_window_size()
            self.z_lift_label.setText("Высота над буквами:")
            self.wrap_btn.setVisible(True)
            if preset_name == "Свободный":
                self.origin_x_spin.setValue(5)
                self.origin_y_spin.setValue(self.field_h - 10)
                self.preview.grid_mode = "cell"
            elif preset_name == "Линейная тетрадь":
                self.font_size_spin.setValue(10)
                self.letter_spacing_spin.setValue(0.0)
                self.line_spacing_spin.setValue(0.8)
                self.humanize_slider.setValue(4)
                self.origin_x_spin.setValue(3)
                self.origin_y_spin.setValue(183)
                self.right_margin_spin.setValue(22.0)
                self.preview.grid_mode = "ruler"
            elif preset_name == "Клеточная тетрадь":
                self.font_size_spin.setValue(10)
                self.letter_spacing_spin.setValue(0.0)
                self.line_spacing_spin.setValue(1.0)
                self.humanize_slider.setValue(4)
                self.origin_x_spin.setValue(5)
                self.origin_y_spin.setValue(187)
                self.right_margin_spin.setValue(25.0)
                self.preview.grid_mode = "cell_empty_top"
            self.trigger_update()

    def load_svg_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите SVG файл", "", "SVG files (*.svg)")
        if not file_path:
            return
        try:
            raw_contours = self.svg_gen.parse_svg_file(file_path)
            if not raw_contours:
                QMessageBox.warning(self, "Внимание", "В файле не найдено ни одного контура.")
                return
            self.svg_raw_contours = raw_contours
            self.svg_filename_label.setText(os.path.basename(file_path))
            all_pts = [pt for contour in raw_contours for pt in contour]
            if all_pts:
                min_x = min(pt[0] for pt in all_pts)
                max_x = max(pt[0] for pt in all_pts)
                min_y = min(pt[1] for pt in all_pts)
                max_y = max(pt[1] for pt in all_pts)
                bbox_w = max_x - min_x
                bbox_h = max_y - min_y
                max_scale_x = (self.field_w * 0.8) / bbox_w if bbox_w > 0 else 1.0
                max_scale_y = (self.field_h * 0.8) / bbox_h if bbox_h > 0 else 1.0
                self.image_scale = min(max_scale_x, max_scale_y, 10.0)
                self.image_scale = max(0.0001, min(10.0, self.image_scale))
                self.image_scale_slider.blockSignals(True)
                self.image_scale_slider.setValue(int(round(self.image_scale * 10000)))
                self.image_scale_slider.blockSignals(False)
                self.image_scale_spin.blockSignals(True)
                self.image_scale_spin.setValue(self.image_scale)
                self.image_scale_spin.blockSignals(False)

                cx = (min_x + max_x) / 2
                cy = (min_y + max_y) / 2
                self.image_offset_x = self.field_w / 2 - cx * self.image_scale
                self.image_offset_y = self.field_h / 2 - cy * self.image_scale

                self.origin_x_spin.setValue(self.image_offset_x)
                self.origin_y_spin.setValue(self.image_offset_y)
            if self.is_image_mode:
                self.preview.set_drag_enabled(True)
            self.update_image_transforms()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить SVG:\n{e}")

    def apply_auto_wrap(self):
        if self.is_image_mode:
            return
        text = self.text_input.toPlainText()
        if not text:
            return
        font_name = self.font_combo.currentText()
        font_path = self.font_manager.get_path(font_name)
        if not font_path:
            return
        size_mm = self.font_size_spin.value()
        spacing = self.letter_spacing_spin.value()
        origin_x = self.origin_x_spin.value()
        right_margin = self.right_margin_spin.value()
        if self.preview.grid_mode in ("ruler", "cell_empty_top"):
            effective_w = 160.0
        else:
            effective_w = self.field_w
        max_line_w = max(10.0, effective_w - origin_x - right_margin)
        try:
            wrapped_text = self.contour_gen.wrap_text_to_string(
                text, font_path, size_mm, spacing, max_line_w
            )
            self.text_input.setPlainText(wrapped_text)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось выполнить перенос: {e}")

    def trigger_update(self):
        if not self.is_image_mode:
            self.debounce_timer.start()

    def update_font_list(self):
        self.font_combo.clear()
        self.font_combo.addItems(self.font_manager.get_names())
        if self.font_combo.count() > 0:
            self.font_combo.setCurrentIndex(0)
        if not self.is_image_mode:
            self.on_param_changed()

    def on_param_changed(self):
        if self.is_image_mode:
            return
        font_name = self.font_combo.currentText()
        font_path = self.font_manager.get_path(font_name)
        if not font_path:
            return
        text = self.text_input.toPlainText()
        size_mm = self.font_size_spin.value()
        spacing = self.letter_spacing_spin.value()
        line_spacing = self.line_spacing_spin.value()
        humanize = self.humanize_slider.value()
        mode = self.mode_combo.currentText()
        origin_x = self.origin_x_spin.value()
        origin_y = self.origin_y_spin.value()
        right_margin = self.right_margin_spin.value()

        if self.preview.grid_mode in ("ruler", "cell_empty_top"):
            effective_w = 160.0
            effective_h = 200.0
        else:
            effective_w = self.field_w
            effective_h = self.field_h

        self.contour_gen.FIELD_W = effective_w
        self.contour_gen.FIELD_H = effective_h

        self.contours = self.contour_gen.generate(
            text, font_path, size_mm, spacing, line_spacing, mode,
            origin_x, origin_y, right_margin, humanize, auto_wrap=False
        )
        origin = (origin_x, origin_y)
        nozzle_offset = (self.nozzle_offset_x, self.nozzle_offset_y)
        grid_mode = self.preview.grid_mode
        if grid_mode == "ruler":
            display_origin_y = origin_y + 1.0
        elif grid_mode == "cell_empty_top":
            display_origin_y = origin_y
        else:
            display_origin_y = origin_y
        origin_for_preview = (origin_x, display_origin_y)
        self.preview.set_data(
            self.contours, origin_for_preview, nozzle_offset, right_margin,
            grid_mode, field_size=(effective_w, effective_h)
        )

    def open_printer_settings(self):
        current_settings = {
            'field_w': self.field_w,
            'field_h': self.field_h,
            'nozzle_offset_x': self.nozzle_offset_x,
            'nozzle_offset_y': self.nozzle_offset_y,
            'travel_speed': self.travel_speed,
            'plunge_speed': self.plunge_speed,
            'engrave_speed': self.engrave_speed
        }
        dlg = PrinterSettingsDialog(self, current_settings)
        if dlg.exec_() == QDialog.Accepted:
            new_settings = dlg.get_settings()
            self.field_w = new_settings['field_w']
            self.field_h = new_settings['field_h']
            self.nozzle_offset_x = new_settings['nozzle_offset_x']
            self.nozzle_offset_y = new_settings['nozzle_offset_y']
            self.travel_speed = new_settings['travel_speed']
            self.plunge_speed = new_settings['plunge_speed']
            self.engrave_speed = new_settings['engrave_speed']
            self.save_printer_settings()
            self.origin_x_spin.setRange(-1000, 1000)
            self.origin_y_spin.setRange(-1000, 1000)
            if self.preset_combo.currentText() == "Свободный":
                self.origin_y_spin.setValue(self.field_h - 10)
            self.contour_gen.FIELD_W = self.field_w
            self.contour_gen.FIELD_H = self.field_h
            self.preview.field_size = (self.field_w, self.field_h)
            if self.is_image_mode:
                self.update_image_transforms()
            else:
                self.trigger_update()

    def generate_and_save_gcode(self):
        if not self.contours:
            QMessageBox.warning(self, "Внимание", "Нет контуров для генерации. Проверьте текст/изображение и настройки.")
            return
        if self.is_image_mode:
            origin_x = self.image_offset_x
            origin_y = self.image_offset_y
        else:
            origin_x = self.origin_x_spin.value()
            origin_y = self.origin_y_spin.value()
        settings = {
            'origin_x': origin_x,
            'origin_y': origin_y,
            'nozzle_offset_x': self.nozzle_offset_x,
            'nozzle_offset_y': self.nozzle_offset_y,
            'z_lift': self.z_lift_spin.value(),
            'approach_z': self.approach_z_spin.value(),
            'z_work': self.z_work_spin.value(),
            'spine_z_offset': self.spine_z_spin.value(),
            'spine_length': self.spine_length_spin.value(),
            'travel_speed': self.travel_speed,
            'plunge_speed': self.plunge_speed,
            'engrave_speed': self.engrave_speed,
        }
        generator = GCodeGenerator(settings)
        gcode = generator.generate(self.contours)
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить G-код", "", "G-code files (*.gcode *.nc *.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(gcode)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{e}")


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("logo.png")))
    app.setStyle('Fusion')
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet("""
        QMainWindow { background-color: #1e1e1e; }
        QWidget { background-color: #1e1e1e; color: #e0e0e0; }
        QGroupBox {
            border: 1px solid #6ef0d4;
            border-radius: 8px;
            margin-top: 10px;
            color: #6ef0d4;
            background-color: #2b2b2b;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }
        QPushButton {
            background-color: #6ef0d4;
            border: none;
            border-radius: 5px;
            padding: 8px;
            color: #1e1e1e;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #8effe6;
        }
        QPushButton:pressed {
            background-color: #52cca8;
        }
        QLineEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {
            background-color: #333333;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
            color: #e0e0e0;
        }
        QTextEdit {
            min-height: 80px;
            border: none;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #333333;
            border: 1px solid #555555;
            selection-background-color: #6ef0d4;
            color: #e0e0e0;
        }
        QLabel {
            background: transparent;
            border: none;
            color: #e0e0e0;
        }
        QCheckBox { color: #e0e0e0; }
        QScrollBar:vertical {
            background: #2b2b2b;
            width: 10px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #6ef0d4;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QSlider {
            background: transparent;
            min-height: 20px;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #555;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #6ef0d4;
            border: none;
            width: 18px;
            height: 18px;
            margin: -6px 0;
            border-radius: 9px;
        }
        QSlider::handle:horizontal:focus {
            border: none;
            background: #6ef0d4;
        }
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()