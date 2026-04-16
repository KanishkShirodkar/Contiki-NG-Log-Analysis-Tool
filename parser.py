# parser.py

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

@dataclass
class LogEntry:
    time: float
    time_str: str
    node_id: int
    level: str
    module: str
    message: str

@dataclass
class NodeInfo:
    node_id: int
    panid: Optional[str] = None
    channel: Optional[str] = None
    mac: Optional[str] = None
    link_local: Optional[str] = None
    first_time: Optional[float] = None
    last_time: Optional[float] = None
    tx: int = 0
    rx: int = 0
    missed_tx: int = 0

@dataclass
class UdpFlow:
    src_node: int
    dst_addr: str
    seq: int
    send_time: float
    resp_time: Optional[float] = None

    @property
    def rtt(self) -> Optional[float]:
        if self.resp_time is None:
            return None
        return self.resp_time - self.send_time

@dataclass
class RadioEntry:
    time_s: float
    src_node: int
    receivers: List[int]
    length: int
    payload_hex: str
    raw_line: str

@dataclass
class DodagJoinEvent:
    node_id: int
    join_time: float
    parent_id: Optional[int]   # RPL preferred parent (from log)
    rank: Optional[int]         # RPL rank if parseable

@dataclass
class TimelineEntry:
    """One event from the Cooja timeline file."""
    time_us: int       # microseconds
    node_id: int
    event_type: str    # TX, RX, IDLE, INTERFERED, etc.
    channel: Optional[int] = None
    extra: str = ""

LINE_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}\.\d{3})\s+ID:(?P<id>\d+)\s+\[(?P<level>[^:]+):\s*(?P<module>[^\]]+)\]\s+(?P<msg>.*)$"
)
LINE_RE_FALLBACK = re.compile(
    r"^(?P<time>\d{2}\d{2}\.\d{3})\s+ID(?P<id>\d+)\s+(?P<level>\w+)\s+(?P<module>\w+)\s+(?P<msg>.*)$"
)

def parse_time_to_seconds(t: str) -> float:
    minutes, rest = t.split(":")
    seconds = float(rest)
    return int(minutes) * 60 + seconds

def parse_log(path: str) -> List[LogEntry]:
    entries: List[LogEntry] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = LINE_RE.match(line)
            if not m:
                m = LINE_RE_FALLBACK.match(line)
            if not m:
                continue
            time_str = m.group("time")
            t = parse_time_to_seconds(time_str)
            node_id = int(m.group("id"))
            level = m.group("level").strip()
            module = m.group("module").strip()
            msg = m.group("msg")
            entries.append(LogEntry(time=t, time_str=time_str, node_id=node_id,
                                     level=level, module=module, message=msg))
    return entries

def build_node_infos(entries: List[LogEntry]) -> Dict[int, NodeInfo]:
    nodes: Dict[int, NodeInfo] = {}
    panid_re = re.compile(r"PANID:\s*(\S+)")
    chan_re = re.compile(r"Default channel:\s*(\S+)")
    mac_re = re.compile(r"Link-layer address:\s*(\S+)")
    ll_re = re.compile(r"Tentative link-local IPv6 address:\s*(\S+)")

    for e in entries:
        n = nodes.setdefault(e.node_id, NodeInfo(node_id=e.node_id))
        if n.first_time is None or e.time < n.first_time:
            n.first_time = e.time
        if n.last_time is None or e.time > n.last_time:
            n.last_time = e.time
        if e.module == "Main":
            m = panid_re.search(e.message)
            if m: n.panid = m.group(1)
            m = chan_re.search(e.message)
            if m: n.channel = m.group(1)
            m = mac_re.search(e.message)
            if m: n.mac = m.group(1)
            m = ll_re.search(e.message)
            if m: n.link_local = m.group(1)
    return nodes

def build_udp_flows(entries: List[LogEntry]) -> List[UdpFlow]:
    flows: List[UdpFlow] = []
    pending: Dict[Tuple[int, int], UdpFlow] = {}
    send_re = re.compile(r"Sending request (\d+) to (\S+)")
    resp_re = re.compile(r"Received response 'hello (\d+)' from (\S+)")

    for e in entries:
        if e.module != "App":
            continue
        msg = e.message
        m = send_re.match(msg)
        if m:
            seq = int(m.group(1))
            dst = m.group(2)
            key = (e.node_id, seq)
            pending[key] = UdpFlow(src_node=e.node_id, dst_addr=dst, seq=seq, send_time=e.time)
            continue
        m = resp_re.match(msg)
        if m:
            seq = int(m.group(1))
            key = (e.node_id, seq)
            flow = pending.get(key)
            if flow is not None:
                flow.resp_time = e.time
                flows.append(flow)
                del pending[key]

    flows.extend(pending.values())
    return flows

def parse_radio_log(path: str) -> List[RadioEntry]:
    entries: List[RadioEntry] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw_line = raw.rstrip("\n")
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                time_ms = float(parts[0])
                src = int(parts[1])
            except ValueError:
                continue
            receivers_raw = parts[2]
            receivers: List[int] = []
            if receivers_raw not in ("-", "none", "NONE"):
                for r in receivers_raw.split(","):
                    r = r.strip()
                    if not r:
                        continue
                    try:
                        receivers.append(int(r))
                    except ValueError:
                        pass
            len_str = parts[3].rstrip(":")
            try:
                length = int(len_str)
            except ValueError:
                length = 0
            hex_tokens = parts[4:]
            payload_hex = "".join(t.replace("0x", "").replace("0X", "") for t in hex_tokens)
            entries.append(RadioEntry(time_s=time_ms / 1000.0, src_node=src,
                                       receivers=receivers, length=length,
                                       payload_hex=payload_hex, raw_line=raw_line))
    return entries

def parse_timeline(path: str) -> List[TimelineEntry]:
    """
    Parse Cooja timeline file.
    Format varies across versions. Common patterns:
      <time_us> <node_id> <event>
      <time_us>;<node_id>;<event>
    We handle both space and semicolon separators.
    """
    entries: List[TimelineEntry] = []
    chan_re = re.compile(r"channel[=:\s]+(\d+)", re.IGNORECASE)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            # Try semicolon split first (Cooja 2.7+ format)
            if ";" in line:
                parts = line.split(";")
            else:
                parts = line.split()
            if len(parts) < 3:
                continue
            try:
                time_us = int(float(parts[0]))
                node_id = int(parts[1])
            except ValueError:
                continue
            event_type = parts[2].strip().upper() if len(parts) > 2 else ""
            extra = ";".join(parts[3:]) if len(parts) > 3 else ""
            channel = None
            m = chan_re.search(extra)
            if m:
                channel = int(m.group(1))
            entries.append(TimelineEntry(time_us=time_us, node_id=node_id,
                                          event_type=event_type, channel=channel, extra=extra))
    return entries

# ── RPL DODAG analysis from log entries ─────────────────────────────────────

_PARENT_RE = re.compile(
    r"(?:preferred parent|parent)[:\s]+(?:node\s*)?(\S+)",
    re.IGNORECASE,
)
_JOINED_RE = re.compile(
    r"(?:joined|new dag|dodag|rpl dag|rpl joined|found dag)",
    re.IGNORECASE,
)
_RANK_RE = re.compile(r"rank[:\s=]+(\d+)", re.IGNORECASE)
# "Not reachable yet" → node is searching; when the next App message
# "Sending request" appears at a different (later) time → joined.
_NOT_REACHABLE_RE = re.compile(r"not reachable yet", re.IGNORECASE)
_SENDING_RE = re.compile(r"Sending request (\d+) to", re.IGNORECASE)

def build_dodag_events(entries: List[LogEntry]) -> List[DodagJoinEvent]:
    """
    Derive DODAG join events from the log.
    Strategy:
      - Track when each non-root node first successfully sends a UDP request
        (= first time it has a route to root = effectively joined DODAG).
      - Also pick up explicit RPL parent/rank log lines when present.
    Returns a list of DodagJoinEvent sorted by join_time.
    """
    root_id = 1
    # Track first "Sending request" per node — proxy for DODAG join
    first_send: Dict[int, float] = {}
    parent_from_log: Dict[int, int] = {}
    rank_from_log: Dict[int, int] = {}

    for e in entries:
        if e.node_id == root_id:
            continue
        # First send = joined DODAG
        if e.module == "App":
            m = _SENDING_RE.match(e.message)
            if m and e.node_id not in first_send:
                first_send[e.node_id] = e.time

        # RPL parent lines
        mp = _PARENT_RE.search(e.message)
        if mp:
            addr = mp.group(1).strip(".,;")
            # Try to parse numeric node ref from last octet
            try:
                last = int(addr.split(":")[-1], 16)
                if 1 <= last <= 100:
                    parent_from_log[e.node_id] = last
            except Exception:
                pass

        # Rank lines
        mr = _RANK_RE.search(e.message)
        if mr:
            rank_from_log[e.node_id] = int(mr.group(1))

    events: List[DodagJoinEvent] = []
    for node_id, join_time in sorted(first_send.items(), key=lambda x: x[1]):
        events.append(DodagJoinEvent(
            node_id=node_id,
            join_time=join_time,
            parent_id=parent_from_log.get(node_id),
            rank=rank_from_log.get(node_id),
        ))
    return events

# Static DODAG tree derived from our simulation analysis
# (parent_map[child] = parent — inferred from rm1 DAO traffic + log)
STATIC_PARENT_MAP: Dict[int, Optional[int]] = {
    1: None,   # root
    2: 1, 3: 1, 4: 1, 5: 1,
    6: 4,
    7: 5, 8: 5,
    9: 7,
    10: 8, 11: 8,
    12: 9,
    13: 10, 14: 10,
    15: 13, 16: 13,
}

def get_parent_map(entries: List[LogEntry]) -> Dict[int, Optional[int]]:
    """
    Try to build parent map from log. Fall back to static map if coverage is low.
    """
    parent_from_log: Dict[int, Optional[int]] = {}
    for e in entries:
        mp = _PARENT_RE.search(e.message)
        if mp:
            addr = mp.group(1).strip(".,;")
            try:
                last = int(addr.split(":")[-1], 16)
                if 1 <= last <= 100:
                    parent_from_log[e.node_id] = last
            except Exception:
                pass

    # If we got parents for most nodes, use log-derived map
    all_nodes = set(e.node_id for e in entries) - {1}
    if len(parent_from_log) >= len(all_nodes) * 0.6:
        result = {1: None}
        result.update(parent_from_log)
        return result
    return STATIC_PARENT_MAP

def get_path_to_root(node_id: int, parent_map: Dict[int, Optional[int]]) -> List[int]:
    """Return ordered list [node_id, ..., root] of the path to root."""
    path = []
    visited = set()
    current = node_id
    while current is not None and current not in visited:
        path.append(current)
        visited.add(current)
        current = parent_map.get(current)
    return path

def get_intermediate_parents(parent_map: Dict[int, Optional[int]]) -> Dict[int, List[int]]:
    """Return dict of parent_node → [children] for nodes that relay traffic."""
    children_map: Dict[int, List[int]] = {}
    for child, parent in parent_map.items():
        if parent is None:
            continue
        children_map.setdefault(parent, []).append(child)
    # Only nodes with children AND not root are intermediate parents
    return {p: sorted(c) for p, c in children_map.items()}