# main.py
import sys
import os
import re
import math
from typing import Optional, List, Dict, Set, Tuple

from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, pyqtSignal, QRectF, QPoint, QTimer
from PyQt6.QtGui import QPalette, QColor, QMouseEvent, QPen, QBrush, QFont, QAction, QPainter
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QTabWidget, QTableView, QMessageBox, QGraphicsScene,
    QGraphicsView, QHeaderView, QPushButton, QMenu, QListWidget, QListWidgetItem,
    QWidgetAction, QAbstractItemView, QFrame, QSplitter, QScrollArea, QSizePolicy,
    QGroupBox, QGridLayout,
)

from parser import (
    parse_log, build_node_infos, build_udp_flows, parse_radio_log,
    parse_timeline, build_dodag_events, get_parent_map, get_path_to_root,
    get_intermediate_parents, NodeInfo, STATIC_PARENT_MAP,
)
from models import (
    LogTableModel, NodeTableModel, FlowTableModel, RadioTableModel,
    DodagJoinModel, IntermediateParentModel,
)

# ── Color constants ──────────────────────────────────────────────────────────
C_ROOT        = QColor("#ffd54f")    # yellow  – root always
C_PARENT      = QColor("#66bb6a")    # green   – intermediate parent
C_LEAF        = QColor("#7ec8ff")    # blue    – leaf/client only
C_SELECTED    = QColor("#ff8c42")    # orange  – selected node
C_PATH        = QColor("#e91e63")    # pink/red – path-to-root edges
C_NEIGHBOR    = QColor("#ffe082")    # pale yellow – radio neighbor of selected
C_PARENT_NODE_HL = QColor("#a5d6a7") # light green – parent chain highlight

# ── Filter proxies ────────────────────────────────────────────────────────────
class BaseFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.node_filter: Optional[Set[int]] = None
        self.text_filter: str = ""
        self.column_value_filters: Dict[int, Optional[Set[str]]] = {}

    def set_node_filter(self, node_ids): self.node_filter = node_ids; self.invalidateFilter()
    def set_text_filter(self, text): self.text_filter = text.lower(); self.invalidateFilter()
    def set_column_filter(self, col, allowed):
        self.column_value_filters[col] = None if allowed is None else set(allowed)
        self.invalidateFilter()
    def clear_column_filter(self, col): self.column_value_filters[col] = None; self.invalidateFilter()
    def clear_all_column_filters(self): self.column_value_filters.clear(); self.invalidateFilter()
    def value_for_column_filter(self, model, row, col, parent):
        v = model.data(model.index(row, col, parent), Qt.ItemDataRole.DisplayRole)
        return "" if v is None else str(v)
    def passes_column_value_filters(self, model, row, parent):
        for col, allowed in self.column_value_filters.items():
            if allowed is None: continue
            if self.value_for_column_filter(model, row, col, parent) not in allowed: return False
        return True

class LogFilterProxy(BaseFilterProxy):
    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if model is None: return True
        if self.node_filter is not None:
            v = model.data(model.index(src_row, 1, src_parent), Qt.ItemDataRole.DisplayRole)
            try:
                if int(v) not in self.node_filter: return False
            except: return False
        if self.text_filter:
            if not any(self.text_filter in str(model.data(model.index(src_row, c, src_parent), Qt.ItemDataRole.DisplayRole) or "").lower() for c in [3, 4]):
                return False
        return self.passes_column_value_filters(model, src_row, src_parent)

class NodeFilterProxy(BaseFilterProxy):
    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if model is None: return True
        if self.node_filter is not None:
            v = model.data(model.index(src_row, 0, src_parent), Qt.ItemDataRole.DisplayRole)
            try:
                if int(v) not in self.node_filter: return False
            except: return False
        if self.text_filter:
            if not any(self.text_filter in str(model.data(model.index(src_row, c, src_parent), Qt.ItemDataRole.DisplayRole) or "").lower() for c in range(1, model.columnCount())):
                return False
        return self.passes_column_value_filters(model, src_row, src_parent)

class FlowFilterProxy(BaseFilterProxy):
    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if model is None: return True
        if self.node_filter is not None:
            v = model.data(model.index(src_row, 0, src_parent), Qt.ItemDataRole.DisplayRole)
            try:
                if int(v) not in self.node_filter: return False
            except: return False
        if self.text_filter:
            if not any(self.text_filter in str(model.data(model.index(src_row, c, src_parent), Qt.ItemDataRole.DisplayRole) or "").lower() for c in range(model.columnCount())):
                return False
        return self.passes_column_value_filters(model, src_row, src_parent)

class RadioFilterProxy(BaseFilterProxy):
    def filterAcceptsRow(self, src_row, src_parent):
        model = self.sourceModel()
        if model is None: return True
        if self.node_filter is not None:
            src_v = model.data(model.index(src_row, 1, src_parent), Qt.ItemDataRole.DisplayRole)
            rx_v  = model.data(model.index(src_row, 2, src_parent), Qt.ItemDataRole.DisplayRole)
            try: src_int = int(src_v)
            except: src_int = None
            rx_set: Set[int] = set()
            for r in str(rx_v or "").split(","):
                try: rx_set.add(int(r.strip()))
                except: pass
            if (src_int is None or src_int not in self.node_filter) and not (rx_set & self.node_filter):
                return False
        if self.text_filter:
            if not any(self.text_filter in str(model.data(model.index(src_row, c, src_parent), Qt.ItemDataRole.DisplayRole) or "").lower() for c in [2, 4]):
                return False
        return self.passes_column_value_filters(model, src_row, src_parent)

class FilterHeader(QHeaderView):
    filterRequested = pyqtSignal(int, QPoint)
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
    def mousePressEvent(self, event):
        section = self.logicalIndexAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.RightButton and section >= 0:
            self.filterRequested.emit(section, event.globalPosition().toPoint()); event.accept(); return
        super().mousePressEvent(event)

# ── Topology view ─────────────────────────────────────────────────────────────
class TopologyView(QGraphicsView):
    nodeClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node_infos: Dict[int, NodeInfo] = {}
        self._positions: Dict[int, Tuple[float, float]] = {}
        self._edges: Dict[Tuple[int, int], int] = {}
        self._neighbors_by_node: Dict[int, Set[int]] = {}
        self._selected_node: Optional[int] = None
        self._parent_map: Dict[int, Optional[int]] = {}
        self._intermediate_parents: Set[int] = set()
        self._radio_entries = []
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._legend_item = None
        self._legend_pos = (15.0, 15.0)

    def set_parent_map(self, parent_map: Dict[int, Optional[int]]):
        self._parent_map = parent_map
        self._intermediate_parents = set(
            p for p in parent_map.values() if p is not None
        )

    def _build_radio_graph(self, radio_entries):
        directed: Dict[Tuple[int,int], int] = {}
        for entry in radio_entries:
            src = entry.src_node
            for rx in entry.receivers:
                if rx == src: continue
                directed[(src, rx)] = directed.get((src, rx), 0) + 1
        undirected: Dict[Tuple[int,int], int] = {}
        seen = set()
        for (a, b), w1 in directed.items():
            pair = tuple(sorted((a, b)))
            if pair in seen: continue
            w2 = directed.get((b, a), 0)
            undirected[pair] = w1 + w2
            seen.add(pair)
        return undirected

    def _build_neighbors(self, node_ids, edges):
        neighbors = {nid: set() for nid in node_ids}
        for (a, b) in edges:
            neighbors[a].add(b); neighbors[b].add(a)
        return neighbors

    def _force_layout(self, node_ids, edges, width=1000, height=700):
        n = len(node_ids)
        if n == 0: return {}
        if n == 1: return {node_ids[0]: (width / 2, height / 2)}
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.34
        positions: Dict[int, List[float]] = {}
        for i, nid in enumerate(sorted(node_ids)):
            angle = 2 * math.pi * i / max(1, n)
            positions[nid] = [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
        max_w = max(edges.values()) if edges else 1
        area = width * height
        k = math.sqrt(area / max(1, n)) * 0.58
        for step in range(260):
            disp = {nid: [0.0, 0.0] for nid in node_ids}
            for i, v in enumerate(node_ids):
                for u in node_ids[i + 1:]:
                    dx = positions[v][0] - positions[u][0]
                    dy = positions[v][1] - positions[u][1]
                    dist = math.hypot(dx, dy) + 0.01
                    force = (k * k) / dist
                    rx = dx / dist * force; ry = dy / dist * force
                    disp[v][0] += rx; disp[v][1] += ry
                    disp[u][0] -= rx; disp[u][1] -= ry
            for (a, b), w in edges.items():
                dx = positions[a][0] - positions[b][0]
                dy = positions[a][1] - positions[b][1]
                dist = math.hypot(dx, dy) + 0.01
                strength = 0.40 + 1.35 * (w / max_w)
                force = (dist * dist / k) * strength
                ax = dx / dist * force; ay = dy / dist * force
                disp[a][0] -= ax; disp[a][1] -= ay
                disp[b][0] += ax; disp[b][1] += ay
            temperature = max(2.0, 20.0 * (1.0 - step / 260.0))
            margin = 70
            for nid in node_ids:
                dx, dy = disp[nid]
                dist = math.hypot(dx, dy)
                if dist > 0:
                    scale = min(temperature, dist) / dist
                    positions[nid][0] += dx * scale
                    positions[nid][1] += dy * scale
                positions[nid][0] = min(width - margin, max(margin, positions[nid][0]))
                positions[nid][1] = min(height - margin, max(margin, positions[nid][1]))
        return {nid: (pos[0], pos[1]) for nid, pos in positions.items()}

    def draw_topology(self, node_infos: List[NodeInfo], radio_entries=None):
        self._node_infos = {n.node_id: n for n in node_infos}
        self._radio_entries = radio_entries or []
        self._selected_node = None
        if not self._node_infos:
            self.setScene(QGraphicsScene(self)); return
        node_ids = sorted(self._node_infos.keys())
        if self._radio_entries:
            self._edges = self._build_radio_graph(self._radio_entries)
            self._neighbors_by_node = self._build_neighbors(node_ids, self._edges)
            self._positions = self._force_layout(node_ids, self._edges)
        else:
            self._edges = {}
            self._neighbors_by_node = {nid: set() for nid in node_ids}
            self._positions = {}
            root_id = 1 if 1 in node_ids else node_ids[0]
            cx, cy, r = 500, 350, 250
            self._positions[root_id] = (cx, cy)
            others = [nid for nid in node_ids if nid != root_id]
            for idx, nid in enumerate(others):
                angle = 2 * math.pi * idx / max(1, len(others))
                self._positions[nid] = (cx + r * math.cos(angle), cy + r * math.sin(angle))
        self._render_scene()

    def _render_scene(self):
        # Save legend position before wiping the scene
        if hasattr(self, '_legend_item') and self._legend_item is not None:
            try:
                pos = self._legend_item.pos()
                self._legend_pos = (pos.x(), pos.y())
            except Exception:
                pass
        scene = QGraphicsScene(self)
        self.setScene(scene)
        node_ids = sorted(self._node_infos.keys())
        if not node_ids: return
        root_id = 1 if 1 in node_ids else node_ids[0]
        selected = self._selected_node
        selected_neighbors = self._neighbors_by_node.get(selected, set()) if selected is not None else set()

        # Path-to-root for selected node
        path_to_root: List[int] = []
        path_edges: Set[Tuple[int,int]] = set()
        if selected is not None and self._parent_map:
            path_to_root = get_path_to_root(selected, self._parent_map)
            for i in range(len(path_to_root) - 1):
                a, b = path_to_root[i], path_to_root[i+1]
                path_edges.add((min(a,b), max(a,b)))

        # Radio range circle
        if selected is not None and selected in self._positions:
            sx, sy = self._positions[selected]
            rr = 135
            scene.addEllipse(QRectF(sx-rr, sy-rr, rr*2, rr*2),
                             QPen(QColor(255,140,0,120), 2, Qt.PenStyle.DashLine),
                             QBrush(QColor(255,200,120,45)))

        # Draw edges
        if self._edges:
            max_w = max(self._edges.values())
            for (a, b), w in sorted(self._edges.items(), key=lambda x: x[1]):
                x1, y1 = self._positions[a]; x2, y2 = self._positions[b]
                pair = (min(a,b), max(a,b))
                if selected is None:
                    alpha = 40 + int(110 * (w / max_w))
                    width = 1.0 + 2.6 * (w / max_w)
                    color = QColor(120, 140, 165, alpha)
                elif pair in path_edges:
                    alpha = 255; width = 4.5; color = C_PATH
                elif a == selected or b == selected:
                    alpha = 230; width = 3.8; color = QColor(255, 120, 0, alpha)
                elif a in selected_neighbors and b in selected_neighbors:
                    alpha = 90; width = 1.6; color = QColor(140, 170, 210, alpha)
                else:
                    alpha = 20; width = 1.0; color = QColor(180, 180, 180, alpha)
                pen = QPen(color, width)
                line = scene.addLine(x1, y1, x2, y2, pen)
                line.setToolTip(f"Radio link {a} ↔ {b}\nSeen together: {w} times")

        # Draw DODAG parent edges (always shown as thin dashed green)
        if self._parent_map:
            for child, parent in self._parent_map.items():
                if parent is None or child not in self._positions or parent not in self._positions:
                    continue
                x1, y1 = self._positions[child]
                x2, y2 = self._positions[parent]
                pair = (min(child,parent), max(child,parent))
                if pair in path_edges and selected is not None:
                    continue  # already drawn as path
                pen = QPen(QColor(30, 180, 80, 140), 1.5, Qt.PenStyle.DotLine)
                scene.addLine(x1, y1, x2, y2, pen)

        # Draw nodes
        for nid in node_ids:
            x, y = self._positions[nid]
            is_root = (nid == root_id)
            is_parent = (nid in self._intermediate_parents)
            info = self._node_infos.get(nid)
            neighbors = self._neighbors_by_node.get(nid, set())
            in_path = (nid in path_to_root)

            if selected is None:
                if is_root:
                    fill = C_ROOT; node_r = 22; border = QColor("#7a5c00"); bw = 2.0
                elif is_parent:
                    fill = C_PARENT; node_r = 19; border = QColor("#1a5c2a"); bw = 2.0
                else:
                    fill = C_LEAF; node_r = 17; border = QColor("#2f3b45"); bw = 1.4
                text_color = Qt.GlobalColor.black
            else:
                if nid == selected:
                    fill = C_SELECTED; node_r = 24; border = QColor("#7a2e00"); bw = 2.6
                    text_color = Qt.GlobalColor.black
                elif in_path and nid != selected:
                    fill = C_PATH; node_r = 21; border = QColor("#880e4f"); bw = 2.2
                    text_color = Qt.GlobalColor.white
                elif nid in selected_neighbors:
                    fill = C_NEIGHBOR; node_r = 20; border = QColor("#a06a00"); bw = 2.0
                    text_color = Qt.GlobalColor.black
                else:
                    fill = QColor(210, 220, 230, 110); node_r = 15 if not is_root else 18
                    border = QColor(130,130,130,100); bw = 1.0
                    text_color = Qt.GlobalColor.darkGray

            circle = scene.addEllipse(QRectF(x-node_r, y-node_r, node_r*2, node_r*2),
                                       QPen(border, bw), QBrush(fill))
            circle.setData(0, nid)

            text = scene.addText(str(nid))
            font = QFont(); font.setPointSize(10)
            font.setBold(nid == selected or is_root or is_parent)
            text.setFont(font)
            text.setDefaultTextColor(text_color)
            tr = text.boundingRect()
            text.setPos(x - tr.width()/2, y - tr.height()/2)
            text.setData(0, nid)

            p = self._parent_map.get(nid)
            role_str = "Root (Server)" if is_root else ("Intermediate Parent" if is_parent else "Leaf (client only)")
            tooltip_lines = [
                f"Node {nid}  [{role_str}]",
                f"RPL Parent: {p if p is not None else '-'}",
                f"IPv6: {info.link_local if info else '-'}",
                f"Tx: {info.tx if info else '-'}  Rx: {info.rx if info else '-'}  Missed: {info.missed_tx if info else '-'}",
                f"Radio neighbors: {len(neighbors)}",
                "Neighbor IDs: " + (", ".join(map(str, sorted(neighbors))) if neighbors else "-"),
            ]
            if in_path and selected is not None and nid != selected:
                tooltip_lines.append(f"← On path to root from Node {selected}")
            circle.setToolTip("\n".join(tooltip_lines))
            text.setToolTip(circle.toolTip())

        # Legend
        if selected is not None and path_to_root:
            path_str = " → ".join(map(str, path_to_root))
            legend_h = 135
        else:
            path_str = ""
            legend_h = 115

        legend_w = 340

        # Use stored legend position if available (so drag persists across redraws)
        if not hasattr(self, '_legend_pos'):
            self._legend_pos = (15.0, 15.0)
        lx, ly = self._legend_pos

        legend_bg = scene.addRect(QRectF(lx, ly, legend_w, legend_h),
                                   QPen(Qt.PenStyle.NoPen), QBrush(Qt.BrushStyle.NoBrush))
        legend_bg.setFlag(legend_bg.GraphicsItemFlag.ItemIsMovable, True)
        legend_bg.setFlag(legend_bg.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        legend_bg.setFlag(legend_bg.GraphicsItemFlag.ItemIsSelectable, False)
        legend_bg.setCursor(Qt.CursorShape.SizeAllCursor)
        legend_bg.setToolTip("Drag to move legend")

        legend = scene.addText("")
        legend.setDefaultTextColor(Qt.GlobalColor.black)
        lf = QFont(); lf.setPointSize(9); legend.setFont(lf)
        legend.setParentItem(legend_bg)

        if selected is None:
            legend.setPlainText(
                "RPL DODAG Topology\n"
                "🟡 Yellow = Root (Node 1)\n"
                "🟢 Green = Intermediate Parent (relay)\n"
                "🔵 Blue = Leaf node (client only)\n"
                "── Dashed green = DODAG parent link\n"
                "Click a node to see path to root"
            )
        else:
            nb_list = sorted(selected_neighbors)
            legend.setPlainText(
                "\n".join([
                    f"Selected: Node {selected}",
                    f"Path to root: {path_str}",
                    f"Radio neighbors: {len(nb_list)}",
                    "🔴 Pink = nodes on path to root",
                    "Click same node to deselect",
                ])
            )
        legend.setPos(8, 6)

        # Resize background rect to always tightly wrap the text content
        text_br = legend.boundingRect()
        actual_w = text_br.width() + 16
        actual_h = text_br.height() + 12
        legend_bg.setRect(QRectF(lx, ly, actual_w, actual_h))

        legend_bg.setZValue(100); legend.setZValue(101)

        # Store legend ref so we can save its position before next redraw
        self._legend_item = legend_bg

        self.setSceneRect(scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene() and not self.sceneRect().isNull():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event: QMouseEvent):
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            node_id = item.data(0)
            if isinstance(node_id, int):
                self._selected_node = None if self._selected_node == node_id else node_id
                self._render_scene()
                self.nodeClicked.emit(node_id)
        super().mousePressEvent(event)


# ── DODAG tab widget ──────────────────────────────────────────────────────────
class DodagAnalysisWidget(QWidget):
    """New tab: DODAG Formation Timeline + Intermediate Parents."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Section 1: Formation Timeline ─────────────────────────────────
        grp1 = QGroupBox("1  DODAG Formation Timeline")
        grp1.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; padding-top: 8px; color: white; }")
        g1l = QVBoxLayout(grp1)

        self.join_table = QTableView()
        self.join_table.setSortingEnabled(True)
        self.join_table.setAlternatingRowColors(False)
        self.join_table.setStyleSheet('QTableView { alternate-background-color: #e8e8e8; background-color: #e8e8e8; }')
        self.join_table.horizontalHeader().setStretchLastSection(True)
        self.join_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        g1l.addWidget(self.join_table)
        layout.addWidget(grp1, 1)

        # ── Section 2: Intermediate Parents ───────────────────────────────
        grp2 = QGroupBox("2  Nodes Acting as Intermediate Parents")
        grp2.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; padding-top: 8px; color: white; }")
        g2l = QVBoxLayout(grp2)

        self.parent_table = QTableView()
        self.parent_table.setSortingEnabled(True)
        self.parent_table.setAlternatingRowColors(False)
        self.parent_table.horizontalHeader().setStretchLastSection(True)
        self.parent_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        g2l.addWidget(self.parent_table)
        layout.addWidget(grp2, 1)

        # ── Color legend ───────────────────────────────────────────────────
        legend_frame = QFrame()
        legend_frame.setFrameShape(QFrame.Shape.StyledPanel)
        legend_frame.setStyleSheet("background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;")
        ll = QHBoxLayout(legend_frame)
        ll.setContentsMargins(12, 6, 12, 6)
        for color_hex, label in [
            ("#1a5276", "Root / Server (Node 1)"),
            ("#1e8449", "Intermediate Parent (relay node)"),
            ("#e8e8e8", "Leaf (client only)"),
        ]:
            dot = QLabel("  ")
            dot.setStyleSheet(f"background: {color_hex}; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;")
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #333;")
            ll.addWidget(dot); ll.addWidget(lbl); ll.addSpacing(16)
        ll.addStretch()
        layout.addWidget(legend_frame, 0)

    def load_data(self, join_events, parent_map):
        join_model = DodagJoinModel(join_events, parent_map)
        self.join_table.setModel(join_model)
        self.join_table.resizeColumnsToContents()

        parent_model = IntermediateParentModel(parent_map, join_events)
        self.parent_table.setModel(parent_model)
        self.parent_table.resizeColumnsToContents()


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, log_path=None, radio_path=None):
        super().__init__()
        self.setWindowTitle("Cooja RPL Log Viewer")
        self.table_proxy_map: Dict[QTableView, BaseFilterProxy] = {}
        self._parent_map: Dict[int, Optional[int]] = {}

        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ── Top filter bar ─────────────────────────────────────────────────
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Node ID filter:"))
        self.node_filter_edit = QLineEdit()
        self.node_filter_edit.setPlaceholderText("e.g. 1,3,5 (empty = all)")
        filter_layout.addWidget(self.node_filter_edit)
        filter_layout.addWidget(QLabel("Text filter:"))
        self.text_filter_edit = QLineEdit()
        self.text_filter_edit.setPlaceholderText("search in module/message/nodes/flows/radio")
        filter_layout.addWidget(self.text_filter_edit)
        self.reset_sort_button = QPushButton("Reset sort")
        filter_layout.addWidget(self.reset_sort_button)
        self.clear_column_filters_button = QPushButton("Clear column filters")
        filter_layout.addWidget(self.clear_column_filters_button)
        main_layout.addLayout(filter_layout)

        # ── Tabs ───────────────────────────────────────────────────────────
        self.tabs = QTabWidget(); main_layout.addWidget(self.tabs)

        self.nodes_table   = QTableView()
        self.flows_table   = QTableView()
        self.radio_table   = QTableView()
        self.log_table     = QTableView()
        self.topology_view = TopologyView()

        # Topology tab with side panel
        self.topology_tab = QWidget()
        topology_layout = QHBoxLayout(self.topology_tab)
        topology_layout.setContentsMargins(8, 8, 8, 8)
        topology_layout.setSpacing(8)

        self.topology_info_box = QFrame()
        self.topology_info_box.setFixedWidth(280)
        self.topology_info_box.setFrameShape(QFrame.Shape.StyledPanel)
        self.topology_info_box.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #cccccc; border-radius: 6px; }")
        info_layout = QVBoxLayout(self.topology_info_box)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(8)

        info_title = QLabel("Node Details")
        info_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #1a1a1a; background: transparent;")
        info_layout.addWidget(info_title)

        self.topology_info_label = QLabel("Click a node to view details.")
        self.topology_info_label.setWordWrap(True)
        self.topology_info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.topology_info_label.setStyleSheet("font-size: 12px; color: #2c2c2c; background: transparent; line-height: 1.6;")
        info_layout.addWidget(self.topology_info_label, 1)

        # Color key inside info panel
        key_frame = QFrame()
        key_frame.setFrameShape(QFrame.Shape.StyledPanel)
        key_frame.setStyleSheet("background: #f0f4f8; border: 1px solid #dde3ea; border-radius: 4px;")
        kl = QVBoxLayout(key_frame)
        kl.setContentsMargins(8, 6, 8, 6); kl.setSpacing(3)
        kl.addWidget(QLabel("<b style='font-size:11px; color:#1a1a1a;'>Node Color Key</b>"))
        for color_hex, label in [
            ("#ffd54f", "Root (Node 1)"),
            ("#66bb6a", "Intermediate Parent"),
            ("#7ec8ff", "Leaf (client only)"),
            ("#ff8c42", "Selected node"),
            ("#e91e63", "Path to root"),
        ]:
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel("  ")
            dot.setStyleSheet(f"background:{color_hex}; border-radius:7px; min-width:14px; max-width:14px; min-height:14px; max-height:14px; border: 1px solid #aaa;")
            lbl = QLabel(label); lbl.setStyleSheet("font-size:11px; color: #2c2c2c;")
            row.addWidget(dot); row.addWidget(lbl); row.addStretch()
            kl.addLayout(row)
        info_layout.addWidget(key_frame)

        topology_layout.addWidget(self.topology_info_box, 0)
        topology_layout.addWidget(self.topology_view, 1)

        # DODAG Analysis tab
        self.dodag_widget = DodagAnalysisWidget()

        self.tabs.addTab(self.nodes_table,   "Nodes")
        self.tabs.addTab(self.flows_table,   "Flows")
        self.tabs.addTab(self.radio_table,   "Radio")
        self.tabs.addTab(self.log_table,     "Raw log")
        self.tabs.addTab(self.topology_tab,  "Topology")
        self.tabs.addTab(self.dodag_widget,  "DODAG Analysis")

        # ── Connections ────────────────────────────────────────────────────
        self.node_filter_edit.textChanged.connect(self.on_filter_changed)
        self.text_filter_edit.textChanged.connect(self.on_filter_changed)
        self.reset_sort_button.clicked.connect(self.on_reset_sort_clicked)
        self.clear_column_filters_button.clicked.connect(self.clear_all_column_filters)
        self.topology_view.nodeClicked.connect(self.on_topology_node_clicked)

        self.entries = []; self.nodes: List[NodeInfo] = []
        self.flows = []; self.radio_entries = []; self.timeline_entries = []

        if log_path is None:
            log_path, _ = QFileDialog.getOpenFileName(self, "Open Cooja loglistener file", "", "Text files (*.txt);;All files (*)")
            if not log_path:
                QMessageBox.warning(self, "No file", "No log file selected, exiting.")
                sys.exit(0)
        self.load_log(log_path, radio_path)

    # ── Filter header ──────────────────────────────────────────────────────
    def install_filter_header(self, table):
        header = FilterHeader(Qt.Orientation.Horizontal, table)
        table.setHorizontalHeader(header)
        header.filterRequested.connect(lambda col, pos, t=table: self.show_column_filter_menu(t, col, pos))

    def show_column_filter_menu(self, table, column, global_pos):
        proxy = self.table_proxy_map.get(table)
        model = proxy.sourceModel() if proxy else None
        if proxy is None or model is None: return
        values = [str(model.data(model.index(r, column), Qt.ItemDataRole.DisplayRole) or "") for r in range(model.rowCount())]
        unique_values = sorted(set(values), key=lambda x: (x == "", x.lower()))
        menu = QMenu(self)
        title = QAction(f"Filter: {model.headerData(column, Qt.Orientation.Horizontal)}", menu)
        title.setEnabled(False); menu.addAction(title)
        current_allowed = proxy.column_value_filters.get(column)
        lw = QListWidget()
        lw.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lw.setMinimumWidth(280)
        lw.setMinimumHeight(min(360, max(160, 28 * min(len(unique_values) + 1, 10))))
        for value in unique_values:
            item = QListWidgetItem(value if value != "" else "(blank)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if current_allowed is None or value in current_allowed else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, value)
            lw.addItem(item)
        wa = QWidgetAction(menu); wa.setDefaultWidget(lw); menu.addAction(wa); menu.addSeparator()
        select_all = menu.addAction("Select all")
        clear_filter = menu.addAction("Clear filter")
        apply_filter = menu.addAction("Apply")
        chosen = menu.exec(global_pos)
        if chosen in (select_all, clear_filter): proxy.clear_column_filter(column); return
        if chosen == apply_filter:
            allowed = {lw.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lw.count()) if lw.item(i).checkState() == Qt.CheckState.Checked}
            if len(allowed) == len(unique_values): proxy.clear_column_filter(column)
            else: proxy.set_column_filter(column, allowed)

    def clear_all_column_filters(self):
        for proxy in self.table_proxy_map.values(): proxy.clear_all_column_filters()

    def on_filter_changed(self, _=None):
        node_text = self.node_filter_edit.text().strip()
        node_ids: Optional[Set[int]] = None
        if node_text:
            ids: Set[int] = set()
            for p in re.split(r"[,\s]+", node_text):
                try: ids.add(int(p))
                except: pass
            if ids: node_ids = ids
        text_filter = self.text_filter_edit.text()
        for proxy in self.table_proxy_map.values():
            proxy.set_node_filter(node_ids); proxy.set_text_filter(text_filter)

    def on_reset_sort_clicked(self): self.apply_default_sort()

    def on_topology_node_clicked(self, node_id: int):
        existing = self.node_filter_edit.text().strip()
        self.node_filter_edit.setText(f"{existing},{node_id}" if existing else str(node_id))
        info = next((n for n in self.nodes if n.node_id == node_id), None)
        neighbor_ids = sorted(self.topology_view._neighbors_by_node.get(node_id, set()))
        neighbor_text = ", ".join(map(str, neighbor_ids)) if neighbor_ids else "-"

        parent_id = self._parent_map.get(node_id)
        path = get_path_to_root(node_id, self._parent_map)
        path_str = " → ".join(map(str, path)) if len(path) > 1 else "Direct to root"
        is_parent = node_id in self.topology_view._intermediate_parents
        root_id = 1
        role_str = ("Root (Server)" if node_id == root_id
                    else "Intermediate Parent (relay)" if is_parent
                    else "Leaf (client only)")
        depth = len(path) - 1

        children = [c for c, p in self._parent_map.items() if p == node_id]

        lines = [
            f"Node: {node_id}",
            f"Role: {role_str}",
            f"RPL Depth: {depth}",
            f"RPL Parent: {parent_id if parent_id is not None else '— (root)'}",
            f"Path to root: {path_str}",
        ]
        if children:
            lines.append(f"Children ({len(children)}): {', '.join(map(str, sorted(children)))}")
        lines += ["──────────────────"]
        if info:
            lines += [
                f"PANID: {info.panid or '-'}",
                f"Channel: {info.channel or '-'}",
                f"MAC: {info.mac or '-'}",
                f"IPv6: {info.link_local or '-'}",
                f"First seen: {f'{info.first_time:.3f}' if info.first_time is not None else '-'} s",
                f"Last seen: {f'{info.last_time:.3f}' if info.last_time is not None else '-'} s",
                f"Tx: {info.tx}  Rx: {info.rx}  Missed: {info.missed_tx}",
            ]
        lines += [
            f"Radio neighbors: {len(neighbor_ids)}",
            f"Neighbor IDs: {neighbor_text}",
        ]
        self.topology_info_label.setText("\n".join(lines))
        if info:
            self.statusBar().showMessage(
                f"Node {node_id} [{role_str}] | IPv6: {info.link_local or '-'} | Tx: {info.tx} Rx: {info.rx} Missed: {info.missed_tx}"
            )
        else:
            self.statusBar().showMessage(f"Node {node_id} [{role_str}] | Depth: {depth} | Parent: {parent_id}")

    # ── Data loading ───────────────────────────────────────────────────────
    def load_log(self, log_path: str, radio_path=None):
        self.entries = parse_log(log_path)
        if not self.entries:
            QMessageBox.warning(self, "Parse error", "No log entries parsed."); return

        nodes_map = build_node_infos(self.entries)
        self.flows = build_udp_flows(self.entries)

        counts: Dict[int, Dict[str, int]] = {}
        for f in self.flows:
            c = counts.setdefault(f.src_node, {"tx": 0, "rx": 0, "missed": 0})
            c["tx"] += 1
            if f.resp_time is not None: c["rx"] += 1
            else: c["missed"] += 1
        for nid, c in counts.items():
            n = nodes_map.setdefault(nid, NodeInfo(node_id=nid))
            n.tx = c["tx"]; n.rx = c["rx"]; n.missed_tx = c["missed"]

        self.nodes = list(nodes_map.values())
        self.radio_entries = []

        # ── Load radio log ─────────────────────────────────────────────────
        candidate_radio = radio_path or os.path.join(os.path.dirname(log_path), "rm.txt")
        if not os.path.exists(candidate_radio): candidate_radio = None
        if candidate_radio and os.path.exists(candidate_radio):
            try:
                self.radio_entries = parse_radio_log(candidate_radio)
            except Exception as e:
                self.statusBar().showMessage(f"Radio log error: {e}")

        # ── Load timeline ──────────────────────────────────────────────────
        self.timeline_entries = []
        candidate_timeline = os.path.join(os.path.dirname(log_path), "timeline")
        if not os.path.exists(candidate_timeline):
            candidate_timeline = os.path.join(os.path.dirname(log_path), "timeline1")
        if os.path.exists(candidate_timeline):
            try:
                self.timeline_entries = parse_timeline(candidate_timeline)
                self.statusBar().showMessage(
                    f"Loaded timeline '{os.path.basename(candidate_timeline)}' with {len(self.timeline_entries)} events"
                )
            except Exception as e:
                self.statusBar().showMessage(f"Timeline parse error: {e}")

        # ── Build DODAG parent map ─────────────────────────────────────────
        self._parent_map = get_parent_map(self.entries)
        self.topology_view.set_parent_map(self._parent_map)

        # ── Build DODAG join events ────────────────────────────────────────
        join_events = build_dodag_events(self.entries)

        # ── Models ────────────────────────────────────────────────────────
        self.log_model   = LogTableModel(self.entries)
        self.nodes_model = NodeTableModel(self.nodes)
        self.flows_model = FlowTableModel(self.flows)
        self.radio_model = RadioTableModel(self.radio_entries)

        self.log_proxy   = LogFilterProxy();   self.log_proxy.setSourceModel(self.log_model)
        self.node_proxy  = NodeFilterProxy();  self.node_proxy.setSourceModel(self.nodes_model)
        self.flow_proxy  = FlowFilterProxy();  self.flow_proxy.setSourceModel(self.flows_model)
        self.radio_proxy = RadioFilterProxy(); self.radio_proxy.setSourceModel(self.radio_model)

        self.table_proxy_map = {
            self.log_table:   self.log_proxy,
            self.nodes_table: self.node_proxy,
            self.flows_table: self.flow_proxy,
            self.radio_table: self.radio_proxy,
        }

        self.log_table.setModel(self.log_proxy)
        self.nodes_table.setModel(self.node_proxy)
        self.flows_table.setModel(self.flow_proxy)
        self.radio_table.setModel(self.radio_proxy)

        for table in (self.log_table, self.nodes_table, self.flows_table, self.radio_table):
            self.install_filter_header(table)
            table.setSortingEnabled(True)
            h = table.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            h.setStretchLastSection(False)
            table.resizeColumnsToContents()

        self.apply_default_sort()
        if self.radio_table.model() and self.radio_table.model().columnCount() >= 5:
            self.radio_table.setColumnWidth(4, 280)

        self.topology_view.draw_topology(self.nodes, self.radio_entries)
        self.dodag_widget.load_data(join_events, self._parent_map)

        self.statusBar().showMessage(
            f"Loaded {len(self.entries)} log lines | {len(self.nodes)} nodes | "
            f"{len(self.flows)} flows | {len(self.radio_entries)} radio frames | "
            f"{len(self.timeline_entries)} timeline events"
        )

    def apply_default_sort(self):
        self.log_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.flows_table.sortByColumn(3, Qt.SortOrder.AscendingOrder)
        self.radio_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.nodes_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("white"))
    palette.setColor(QPalette.ColorRole.Base, QColor("white"))
    palette.setColor(QPalette.ColorRole.Text, QColor("black"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("black"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QTabBar::tab { color: #222; padding: 6px 14px; font-size: 13px; }
        QTabBar::tab:selected { font-weight: bold; color: #01696f; border-bottom: 2px solid #01696f; }
        QGroupBox { border: 1px solid #ccc; border-radius: 6px; margin-top: 8px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
        QScrollBar:vertical { background: #f0f0f0; width: 12px; }
        QScrollBar::handle:vertical { background: #d0d0d0; min-height: 20px; border-radius: 4px; }
        QScrollBar::handle:vertical:hover { background: #b0b0b0; }
        QScrollBar:horizontal { background: #f0f0f0; height: 12px; }
        QScrollBar::handle:horizontal { background: #d0d0d0; min-width: 20px; border-radius: 4px; }
        QScrollBar::handle:horizontal:hover { background: #b0b0b0; }
    """)

    log_path   = sys.argv[1] if len(sys.argv) > 1 else None
    radio_path = sys.argv[2] if len(sys.argv) > 2 else None

    win = MainWindow(log_path, radio_path)
    win.resize(1400, 800)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()