# Cooja RPL Log Analyzer

A desktop GUI tool for analyzing **RPL (IPv6 Routing Protocol for Low-Power and Lossy Networks)**
simulation output from the **Cooja simulator** (Contiki-NG). It parses your three Cooja log files,
then presents the data across interactive tabs — topology graph, node table, UDP flows, raw radio
frames, DODAG analysis, and a timeline view.

---

## File Structure

```
project/
├── launcher.py        ← Start here — file picker, then launches main.py
├── main.py            ← Main GUI window (tabs, topology, DODAG, filters)
├── parser.py          ← Log parsers for all three file formats
├── model.py           ← Qt table models (LogTableModel, NodeTableModel, …)
└── README.md
```

---

## Requirements

- Python 3.9 or newer
- PyQt6

---

## Quick Start

### 1 — First-time setup (create virtual environment)

```bash
cd /path/to/project
python3 -m venv venv
```

### 2 — Activate the virtual environment

```bash
source venv/bin/activate
```

> On Windows use: `venv\Scripts\activate`

### 3 — Install dependencies (first time inside venv only)

```bash
pip install PyQt6
```

### 4 — Run the launcher

```bash
python launcher.py
```

---

## Using the Launcher

The launcher window has **three file fields**. Each one requires a specific Cooja output file:

| Field | File | Notes |
|---|---|---|
| **Mote Output Log** | `loglistener.txt` | Required — main RPL/UDP log from Cooja's Log Listener plugin |
| **Radio Log** | `rm` | Required — radio medium log from Cooja |
| **Timeline / TimeDetail** | `timedetail` | Required — timeline events exported from Cooja |

**To select each file**, either:
- Click the **Browse…** button next to the field, or
- **Drag and drop** the file directly onto the field from your file manager.

Once all three fields are filled, click **Open Analyzer**.

The launcher will run:

```bash
python main.py loglistener.txt rm timedetail
```

using the currently active Python interpreter (your venv), and the full analyzer window will open.

---

## Generating the Three Log Files in Cooja

Inside a Cooja simulation:

### loglistener.txt — Mote Output Log
1. Open **Tools → Log Listener**
2. Run the simulation
3. Click **File → Save to file** → save as `loglistener.txt`

### rm — Radio Log
1. Open **Tools → Radio Logger**
2. Run the simulation
3. Click **File → Save to file** → save as `rm`

### timedetail — Timeline Log
1. Open **Tools → Timeline**
2. Run the simulation
3. Right-click the timeline → **Save to file** → save as `timedetail`

---

## Analyzer Tabs

Once loaded, the main window shows six tabs:

### Nodes
Table of all detected motes — node ID, role (root / parent / leaf),
DODAG rank, preferred parent, hop count, and total packets sent.

### Flows
Per-node UDP flow summary — source, destination, packet count, and
sequence number range.

### Radio
Radio frame log — source node, receivers, RSSI, and payload summary.
Supports right-click column filters and text search.

### Raw Log
Full contents of `loglistener.txt`, displayed line by line.
Searchable by node ID, module name, or any keyword.

### Topology
Interactive force-directed graph of the RPL DODAG:
- **Click any node** to highlight its path to the root (shown in pink/red),
  its preferred parent (green), and its radio neighbors.
- The **side panel** shows that node's rank, hop count, parent, and role.
- Drag to pan, scroll to zoom.

**Node color key:**

| Color | Meaning |
|---|---|
| 🟡 Yellow | Root (Node 1 / DODAG sink) |
| 🟢 Green | Intermediate parent (relays traffic) |
| 🔵 Blue | Leaf node (client only) |
| 🟠 Orange | Currently selected node |
| 🔴 Pink/Red | Path-to-root edges from selected node |

### DODAG Analysis
Two sub-tables derived from the RPL control messages:
- **DODAG Join Events** — which node joined when, and which parent it chose
- **Intermediate Parents** — nodes that act as relay/parent, how many children each has

---

## Filters and Search

### Global filters (top bar)
| Control | Effect |
|---|---|
| **Node ID filter** | Show only specific nodes, e.g. `1,3,5` |
| **Text filter** | Search across module names and messages |
| **Reset sort** | Return all tables to default sort order |
| **Clear column filters** | Remove any active column-level filters |

### Per-column filters (right-click column header)
Right-click any column header in any table to filter by the values in that column.

---

## Running Without the Launcher (CLI mode)

You can also run the analyzer directly from the terminal, passing the three file paths as arguments:

```bash
source venv/bin/activate
python main.py loglistener.txt rm timedetail
```

All three arguments are required for full functionality. If only the first argument is given,
the radio and timeline features will be empty but the tool will still open.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: PyQt6` | Run `pip install PyQt6` inside the activated venv |
| Launcher says `main.py not found` | Make sure `launcher.py` is in the same folder as `main.py` |
| Topology shows no edges | The `rm` radio log is missing or empty — check the Radio Logger export |
| Timeline tab is empty | The `timedetail` file is missing or was not exported correctly from Cooja |
| Window opens but no data loads | Check the terminal output for parsing errors — the log format must match Contiki-NG defaults |

---

## Project Context

This tool was built to assist with research on RPL behavior in Contiki-NG / Cooja simulations.
It visualizes:
- DODAG formation and parent selection
- Hop-by-hop paths from leaf nodes to the DODAG root
- Radio link quality between motes
- UDP flow delivery statistics

Protocol reference: **RFC 6550 — RPL: IPv6 Routing Protocol for Low-Power and Lossy Networks**
(IETF Standards Track, March 2012).
