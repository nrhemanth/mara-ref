#!/usr/bin/env python3
"""
visualize_simulate.py — Run opentrons_simulate and render a visual summary.

Usage:
    python runs/visualize_simulate.py modules/mara_mof_singlefile.py
    python runs/visualize_simulate.py modules/mara_mof_singlefile.py --out run_summary.png
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec


# ── Flex deck: 4 rows (A-D) × 3 cols (1-3), row A at top ─────────────────────
FLEX_ROWS = ["A", "B", "C", "D"]
FLEX_COLS = [1, 2, 3]

LABWARE_PALETTE = {
    "tip rack":   "#AED6F1",
    "tough 96":   "#A9DFBF",
    "96 well":    "#A9DFBF",
    "6 well":     "#F9E79F",
    "trash":      "#E8DAEF",
    "reservoir":  "#FDEBD0",
}

SLOT_SHORT = {
    "Opentrons Flex 96 Tip Rack 200 µL": "Tip Rack\n200 µL",
    "Opentrons Tough 96 Well Plate 200 µL PCR Full Skirt": "96-Well\nPlate",
    "Corning 6 Well Plate 16.8 mL Flat": "6-Well\nPlate",
    "Trash Bin": "Trash\nBin",
}


def slot_color(labware: str) -> str:
    lo = labware.lower()
    for key, color in LABWARE_PALETTE.items():
        if key in lo:
            return color
    return "#D5D8DC"


# ── Parser ────────────────────────────────────────────────────────────────────

_ASP = re.compile(r"Aspirating ([\d.]+) uL from ([A-Z]\d+) of (.+?) on slot ([A-D]\d)")
_DSP = re.compile(r"Dispensing ([\d.]+) uL into ([A-Z]\d+) of (.+?) on slot ([A-D]\d)")
_MIX = re.compile(r"Mixing (\d+) times with a volume of ([\d.]+) ul")
_MIX_WELL = re.compile(r"(?:Aspirating|Dispensing) [\d.]+ uL (?:from|into) ([A-Z]\d+) of (.+?) on slot ([A-D]\d)")
_PKP = re.compile(r"Picking up tip from [A-Z]\d+ of (.+?) on slot ([A-D]\d)")
_TRB = re.compile(r"Trash Bin on slot ([A-D]\d)")
_SEC = re.compile(r"^(=== .+ ===|Step \S+:.+|.+ completed!)")


def parse_log(text: str):
    """
    Returns:
        labware_map  {slot -> display_name}
        transfers    list of {type, volume, well, slot, labware}
        sections     list of section header strings (in order)
    """
    labware_map = {}
    transfers   = []
    sections    = []
    in_mix      = False
    mix_well    = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Section comments
        if _SEC.match(line):
            sections.append(line)
            in_mix = False
            continue

        # Trash bin slot
        m = _TRB.search(line)
        if m:
            labware_map[m.group(1)] = "Trash Bin"

        # Aspirate
        m = _ASP.match(line)
        if m:
            vol, well, lw, slot = m.groups()
            labware_map[slot] = lw
            entry = {"type": "aspirate", "volume": float(vol),
                     "well": well, "slot": slot, "labware": lw}
            if in_mix and mix_well:
                entry["mix_context"] = True
            transfers.append(entry)
            continue

        # Pick up tip (registers tip rack in labware_map)
        m = _PKP.match(line)
        if m:
            lw, slot = m.groups()
            labware_map[slot] = lw

        # Dispense
        m = _DSP.match(line)
        if m:
            vol, well, lw, slot = m.groups()
            labware_map[slot] = lw
            entry = {"type": "dispense", "volume": float(vol),
                     "well": well, "slot": slot, "labware": lw}
            if in_mix and mix_well:
                entry["mix_context"] = True
            transfers.append(entry)
            continue

        # Mix header — the indented lines inside are aspirate/dispense
        m = _MIX.match(line)
        if m:
            in_mix = True
            transfers.append({"type": "mix", "cycles": int(m.group(1)),
                               "volume": float(m.group(2))})
            continue

        # Exit mix context when we see a non-indented, non-blank action
        if in_mix and not line.startswith(" "):
            in_mix = False

    return labware_map, transfers, sections


# ── Drawing helpers ───────────────────────────────────────────────────────────

def draw_deck(ax, labware_map: dict):
    ax.set_xlim(-0.55, 2.55)
    ax.set_ylim(-0.55, 3.55)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Deck Layout", fontsize=12, fontweight="bold", pad=8)

    for ri, row in enumerate(FLEX_ROWS):
        for ci, col in enumerate(FLEX_COLS):
            slot = f"{row}{col}"
            x = ci
            y = 3 - ri  # A at top

            lw    = labware_map.get(slot, "")
            color = slot_color(lw) if lw else "#F2F3F4"
            short = SLOT_SHORT.get(lw, "\n".join(lw.split()[:3])) if lw else ""

            rect = mpatches.FancyBboxPatch(
                (x - 0.46, y - 0.46), 0.92, 0.92,
                boxstyle="round,pad=0.06",
                facecolor=color, edgecolor="#95A5A6", linewidth=1.4,
            )
            ax.add_patch(rect)

            # Slot label (top-left corner)
            ax.text(x - 0.39, y + 0.37, slot, fontsize=7.5,
                    color="#717D7E", va="top", ha="left", fontweight="bold")

            # Labware short name
            if short:
                ax.text(x, y - 0.04, short, fontsize=7.5,
                        ha="center", va="center",
                        multialignment="center", color="#1A252F")

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=c, edgecolor="#95A5A6", label=k.title())
        for k, c in LABWARE_PALETTE.items()
    ]
    ax.legend(handles=legend_items, loc="lower center",
              bbox_to_anchor=(0.5, -0.14), ncol=3,
              fontsize=7, framealpha=0.8)


def draw_transfer_table(ax, transfers: list):
    ax.axis("off")
    ax.set_title("Liquid Transfer Summary", fontsize=12, fontweight="bold", pad=8)

    # Aggregate: slot/well → {aspirated, dispensed, mix_vol, labware}
    agg = defaultdict(lambda: {"asp": 0.0, "dsp": 0.0, "mix": 0.0, "labware": ""})

    for t in transfers:
        if t["type"] in ("aspirate", "dispense") and not t.get("mix_context"):
            key = f"{t['slot']} / {t['well']}"
            if t["type"] == "aspirate":
                agg[key]["asp"] += t["volume"]
            else:
                agg[key]["dsp"] += t["volume"]
            agg[key]["labware"] = t["labware"]
        elif t["type"] == "mix":
            pass  # shown inline in note column

    # Add mix rows
    mix_wells = defaultdict(lambda: {"cycles": 0, "vol": 0.0, "labware": ""})
    in_mix = False
    for t in transfers:
        if t["type"] == "mix":
            in_mix = True
            _mix_cycles = t["cycles"]
            _mix_vol    = t["volume"]
        elif t["type"] in ("aspirate", "dispense") and t.get("mix_context"):
            key = f"{t['slot']} / {t['well']}"
            mix_wells[key]["cycles"]  = _mix_cycles
            mix_wells[key]["vol"]     = _mix_vol
            mix_wells[key]["labware"] = t["labware"]
        elif t["type"] in ("aspirate", "dispense"):
            in_mix = False

    rows = []
    for key in sorted(agg):
        d = agg[key]
        short_lw = d["labware"].split()[-1] if d["labware"] else ""
        rows.append([
            key,
            d["labware"][:28] + "…" if len(d["labware"]) > 28 else d["labware"],
            f"{d['asp']:.1f}" if d["asp"] else "—",
            f"{d['dsp']:.1f}" if d["dsp"] else "—",
            "",
        ])

    for key in sorted(mix_wells):
        d = mix_wells[key]
        rows.append([
            key,
            d["labware"][:28] + "…" if len(d["labware"]) > 28 else d["labware"],
            "—", "—",
            f"{d['cycles']}× {d['vol']:.0f} µL",
        ])

    if not rows:
        ax.text(0.5, 0.5, "No transfer data found.", ha="center", va="center",
                transform=ax.transAxes, fontsize=10, color="#7F8C8D")
        return

    rows.sort(key=lambda r: r[0])
    col_labels = ["Slot / Well", "Labware", "Aspirated (µL)", "Dispensed (µL)", "Mix"]

    tbl = ax.table(
        cellText=rows,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.55)
    tbl.auto_set_column_width(list(range(len(col_labels))))

    # Header style
    for j in range(len(col_labels)):
        cell = tbl[0, j]
        cell.set_facecolor("#2C3E50")
        cell.get_text().set_color("white")
        cell.get_text().set_fontweight("bold")

    # Row zebra striping
    for i in range(1, len(rows) + 1):
        bg = "#EBF5FB" if i % 2 == 0 else "white"
        for j in range(len(col_labels)):
            tbl[i, j].set_facecolor(bg)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Visualize opentrons_simulate output.")
    parser.add_argument("protocol", help="Protocol .py file path")
    parser.add_argument("--out", default=None, help="Output image path (default: <protocol>_simulation.png)")
    args = parser.parse_args()

    protocol_path = Path(args.protocol)
    if not protocol_path.exists():
        sys.exit(f"Protocol file not found: {protocol_path}")

    # Run simulation
    print(f"Simulating {protocol_path.name} ...")
    result = subprocess.run(
        ["opentrons_simulate", str(protocol_path)],
        capture_output=True, text=True,
    )
    log_text = result.stdout
    if result.returncode != 0 and not log_text.strip():
        print("Simulation failed:\n", result.stderr[:600])
        sys.exit(1)

    labware_map, transfers, sections = parse_log(log_text)

    # Build figure
    fig = plt.figure(figsize=(15, 6.5))
    fig.patch.set_facecolor("#FDFEFE")
    fig.suptitle(
        f"Simulation: {protocol_path.name}",
        fontsize=14, fontweight="bold", y=1.01,
    )

    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 2.4], wspace=0.08)
    ax_deck  = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])

    draw_deck(ax_deck, labware_map)
    draw_transfer_table(ax_table, transfers)

    out_path = args.out or str(protocol_path.with_stem(protocol_path.stem + "_simulation").with_suffix(".png"))
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
