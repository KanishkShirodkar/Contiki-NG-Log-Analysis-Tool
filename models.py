# models.py

from typing import List, Any, Optional, Dict
from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt6.QtGui import QColor

from parser import LogEntry, NodeInfo, UdpFlow, RadioEntry, DodagJoinEvent


class LogTableModel(QAbstractTableModel):
    def __init__(self, entries: List[LogEntry]):
        super().__init__()
        self._entries = entries
        self._headers = ["Time", "Node", "Level", "Module", "Message"]

    def rowCount(self, parent=QModelIndex()): return len(self._entries)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole): return QVariant()
        e = self._entries[index.row()]
        col = index.column()
        if col == 0: return e.time_str
        elif col == 1: return e.node_id
        elif col == 2: return e.level
        elif col == 3: return e.module
        elif col == 4: return e.message
        return QVariant()

    def entry_at(self, row): return self._entries[row]


class NodeTableModel(QAbstractTableModel):
    def __init__(self, nodes: List[NodeInfo]):
        super().__init__()
        self._nodes = nodes
        self._headers = ["Node", "PANID", "Channel", "MAC", "Link-local IPv6",
                         "First time (s)", "Last time (s)", "Tx", "Rx", "MissedTx"]

    def rowCount(self, parent=QModelIndex()): return len(self._nodes)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole): return QVariant()
        n = self._nodes[index.row()]
        col = index.column()
        if col == 0: return n.node_id
        elif col == 1: return n.panid or ""
        elif col == 2: return n.channel or ""
        elif col == 3: return n.mac or ""
        elif col == 4: return n.link_local or ""
        elif col == 5: return f"{n.first_time:.3f}" if n.first_time is not None else ""
        elif col == 6: return f"{n.last_time:.3f}" if n.last_time is not None else ""
        elif col == 7: return n.tx
        elif col == 8: return n.rx
        elif col == 9: return n.missed_tx
        return QVariant()


class FlowTableModel(QAbstractTableModel):
    def __init__(self, flows: List[UdpFlow]):
        super().__init__()
        self._flows = flows
        self._headers = ["Src node", "Dst addr", "Seq", "Send time (s)", "Resp time (s)", "RTT (s)", "Success"]

    def rowCount(self, parent=QModelIndex()): return len(self._flows)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole): return QVariant()
        f = self._flows[index.row()]
        col = index.column()
        if col == 0: return f.src_node
        elif col == 1: return f.dst_addr
        elif col == 2: return f.seq
        elif col == 3: return f"{f.send_time:.3f}"
        elif col == 4: return f"{f.resp_time:.3f}" if f.resp_time is not None else ""
        elif col == 5: return f"{f.rtt:.3f}" if f.rtt is not None else ""
        elif col == 6: return "Yes" if f.resp_time is not None else "No"
        return QVariant()

    def flow_at(self, row): return self._flows[row]


class RadioTableModel(QAbstractTableModel):
    def __init__(self, entries: List[RadioEntry]):
        super().__init__()
        self._entries = entries
        self._headers = ["Time (s)", "Src node", "Receivers", "Length", "Payload (hex)"]

    def rowCount(self, parent=QModelIndex()): return len(self._entries)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole): return QVariant()
        e = self._entries[index.row()]
        col = index.column()
        if col == 0: return f"{e.time_s:.3f}"
        elif col == 1: return e.src_node
        elif col == 2: return ",".join(str(r) for r in e.receivers)
        elif col == 3: return e.length
        elif col == 4: return e.payload_hex
        return QVariant()


class DodagJoinModel(QAbstractTableModel):
    """Table model for the DODAG Formation Timeline tab."""
    def __init__(self, events: List[DodagJoinEvent], parent_map: Dict):
        super().__init__()
        self._events = events
        self._parent_map = parent_map
        self._headers = ["Node", "Join Time (s)", "RPL Parent", "RPL Depth", "Role"]

    def rowCount(self, parent=QModelIndex()): return len(self._events)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def _depth(self, node_id):
        """Hop count from root."""
        depth = 0
        current = node_id
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            current = self._parent_map.get(current)
            if current is not None:
                depth += 1
        return depth

    def _role(self, node_id):
        is_parent = any(p == node_id for p in self._parent_map.values() if p is not None)
        if node_id == 1:
            return "Root (Server)"
        elif is_parent:
            return "Intermediate Parent"
        return "Leaf (Client only)"

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        e = self._events[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.BackgroundRole:
            r = self._role(e.node_id)
            if r == "Root (Server)": return QColor("#1a5276")
            elif r == "Intermediate Parent": return QColor("#1e8449")
            return QColor("#e8e8e8")

        if role == Qt.ItemDataRole.ForegroundRole:
            r = self._role(e.node_id)
            if r in ("Root (Server)", "Intermediate Parent"): return QColor("white")
            return QColor("#2c2c2c")

        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return QVariant()

        if col == 0: return e.node_id
        elif col == 1: return f"{e.join_time:.3f}"
        elif col == 2:
            p = self._parent_map.get(e.node_id)
            return str(p) if p is not None else "-"
        elif col == 3: return self._depth(e.node_id)
        elif col == 4: return self._role(e.node_id)
        return QVariant()


class IntermediateParentModel(QAbstractTableModel):
    """Table model for the Intermediate Parents tab."""
    def __init__(self, parent_map: Dict, join_events: List[DodagJoinEvent]):
        super().__init__()
        # Build rows: one per intermediate parent node
        from parser import get_intermediate_parents
        children_map = get_intermediate_parents(parent_map)
        join_time_map = {e.node_id: e.join_time for e in join_events}
        self._rows = []
        for parent_id in sorted(children_map.keys()):
            children = children_map[parent_id]
            depth = 0
            current = parent_id
            visited = set()
            while current is not None and current not in visited:
                visited.add(current)
                current = parent_map.get(current)
                if current is not None:
                    depth += 1
            join_t = join_time_map.get(parent_id)
            self._rows.append({
                "node": parent_id,
                "children": children,
                "depth": depth,
                "join_time": join_t,
                "is_root": parent_id == 1,
            })
        self._headers = ["Parent Node", "Role", "RPL Depth", "Children", "Children IDs", "Join Time (s)"]

    def rowCount(self, parent=QModelIndex()): return len(self._rows)
    def columnCount(self, parent=QModelIndex()): return len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole: return QVariant()
        if orientation == Qt.Orientation.Horizontal: return self._headers[section]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return QVariant()
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.BackgroundRole:
            if row["is_root"]: return QColor("#1a5276")
            return QColor("#1e8449")

        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor("white")

        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return QVariant()

        if col == 0: return row["node"]
        elif col == 1: return "Root (Server)" if row["is_root"] else "Intermediate Parent"
        elif col == 2: return row["depth"]
        elif col == 3: return len(row["children"])
        elif col == 4: return ", ".join(map(str, row["children"]))
        elif col == 5:
            jt = row["join_time"]
            return f"{jt:.3f}" if jt is not None else ("0.000" if row["is_root"] else "-")
        return QVariant()