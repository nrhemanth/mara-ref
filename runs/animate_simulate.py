#!/usr/bin/env python3
"""
animate_simulate.py — Step-by-step animated visualizer for Opentrons Flex protocols.

Runs opentrons_simulate, parses the log, and renders an animated GIF where
each frame shows one operation with the active deck slot(s) highlighted.

Usage:
    python runs/animate_simulate.py modules/mara_mof_singlefile.py
    python runs/animate_simulate.py modules/mara_mof_singlefile.py --fps 1 --out run.gif
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.gridspec import GridSpec


# ── Deck geometry ─────────────────────────────────────────────────────────────

FLEX_ROWS = ["A", "B", "C", "D"]      # A at top visually
FLEX_COLS = [1, 2, 3]

SLOT_SHORT = {
    "Opentrons Flex 96 Tip Rack 200 µL":                    "Tip Rack\n200 µL",
    "Opentrons Tough 96 Well Plate 200 µL PCR Full Skirt":  "96-Well\nPlate",
    "Corning 6 Well Plate 16.8 mL Flat":                   "6-Well\nPlate",
    "Trash Bin":                                            "Trash\nBin",
}

# Base fill colors (idle state)
_BASE = {
    "tip rack": "#AED6F1",
    "tough 96": "#A9DFBF",
    "96 well":  "#A9DFBF",
    "6 well":   "#F9E79F",
    "trash":    "#E8DAEF",
}
# Activated fill colors
_ACTIVE = {
    "tip rack": "#2980B9",
    "tough 96": "#1E8449",
    "96 well":  "#1E8449",
    "6 well":   "#D35400",
    "trash":    "#7D3C98",
}

ACTION_COLOR = {
    "section":    "#2C3E50",
    "configure":  "#7F8C8D",
    "pickup_tip": "#2980B9",
    "drop_tip":   "#7D3C98",
    "aspirate":   "#C0392B",
    "dispense":   "#1E8449",
    "mix":        "#6C3483",
}
ACTION_ICON = {
    "section":    "▶",
    "configure":  "⚙",
    "pickup_tip": "↓ tip",
    "drop_tip":   "↑ tip",
    "aspirate":   "◀ aspirate",
    "dispense":   "▶ dispense",
    "mix":        "↺ mix",
}


def _slot_xy(slot: str) -> tuple[float, float]:
    ri = FLEX_ROWS.index(slot[0])
    ci = int(slot[1]) - 1
    return float(ci), float(3 - ri)


def _lw_color(lw: str, active: bool) -> str:
    palette = _ACTIVE if active else _BASE
    lo = lw.lower()
    for k, c in palette.items():
        if k in lo:
            return c
    return "#AAB7B8" if active else "#EAECEE"


# ── Log parser ────────────────────────────────────────────────────────────────

_RE_ASP  = re.compile(r"Aspirating ([\d.]+) uL from ([A-Z]\d+) of (.+?) on slot ([A-D]\d)")
_RE_DSP  = re.compile(r"Dispensing ([\d.]+) uL into ([A-Z]\d+) of (.+?) on slot ([A-D]\d)")
_RE_MIX  = re.compile(r"Mixing (\d+) times with a volume of ([\d.]+) ul")
_RE_PKP  = re.compile(r"Picking up tip from [A-Z]\d+ of (.+?) on slot ([A-D]\d)")
_RE_DRP  = re.compile(r"Dropping tip into (.+?) on slot ([A-D]\d)")
_RE_CONF = re.compile(r"Configure pipette .+ to use NozzleLayout\.(\w+)")
_RE_TRB  = re.compile(r"Trash Bin on slot ([A-D]\d)")
_RE_SEC  = re.compile(r"(=== .+? ===|Step [\d.]+: .+|.+ completed!)")


def parse_log(text: str) -> tuple[dict, list]:
    """
    Returns:
        labware_map  {slot → labware display name}
        frames       list of frame dicts
    """
    labware_map: dict[str, str] = {}
    frames: list[dict] = []
    in_mix = False
    mix_frame: dict | None = None
    last_src_slot: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Register trash bin slot
        m = _RE_TRB.search(line)
        if m:
            labware_map[m.group(1)] = "Trash Bin"

        # ── Section header ─────────────────────────────────────────────
        m = _RE_SEC.match(line)
        if m:
            in_mix = False
            frames.append({
                "type": "section",
                "slots": [],
                "title": line.strip("= "),
                "detail": "",
                "arrow": None,
            })
            continue

        # ── Configure ──────────────────────────────────────────────────
        m = _RE_CONF.match(line)
        if m:
            frames.append({
                "type": "configure",
                "slots": [],
                "title": f"Configure nozzle: {m.group(1).lower()} mode",
                "detail": "",
                "arrow": None,
            })
            continue

        # ── Pick up tip ────────────────────────────────────────────────
        m = _RE_PKP.match(line)
        if m:
            lw, slot = m.group(1), m.group(2)
            labware_map[slot] = lw
            frames.append({
                "type": "pickup_tip",
                "slots": [slot],
                "title": "Pick up tip",
                "detail": f"slot {slot}  ·  {SLOT_SHORT.get(lw, lw)}",
                "arrow": None,
            })
            continue

        # ── Drop tip ───────────────────────────────────────────────────
        m = _RE_DRP.match(line)
        if m:
            lw, slot = m.group(1), m.group(2)
            labware_map[slot] = lw
            in_mix = False
            frames.append({
                "type": "drop_tip",
                "slots": [slot],
                "title": "Drop tip",
                "detail": f"slot {slot}  ·  {SLOT_SHORT.get(lw, lw)}",
                "arrow": None,
            })
            continue

        # ── Mix block header ───────────────────────────────────────────
        m = _RE_MIX.match(line)
        if m:
            in_mix = True
            mix_frame = {
                "type": "mix",
                "slots": [],
                "title": f"Mix  {m.group(1)}×  @  {float(m.group(2)):.0f} µL",
                "detail": "",
                "arrow": None,
            }
            frames.append(mix_frame)
            continue

        # ── Indented aspirate/dispense inside mix — update mix frame ───
        if in_mix and raw_line.startswith("        "):
            for pat in (_RE_ASP, _RE_DSP):
                mm = pat.match(line)
                if mm:
                    vol, well, lw, slot = mm.groups()
                    labware_map[slot] = lw
                    if slot not in mix_frame["slots"]:
                        mix_frame["slots"].append(slot)
                    mix_frame["detail"] = (
                        f"well {well}  ·  slot {slot}\n"
                        f"{SLOT_SHORT.get(lw, lw)}"
                    )
            continue

        # ── Top-level aspirate ─────────────────────────────────────────
        m = _RE_ASP.match(line)
        if m:
            in_mix = False
            vol, well, lw, slot = m.groups()
            labware_map[slot] = lw
            last_src_slot = slot
            frames.append({
                "type": "aspirate",
                "slots": [slot],
                "title": f"Aspirate  {float(vol):.1f} µL",
                "detail": f"from {well}  ·  slot {slot}\n{SLOT_SHORT.get(lw, lw)}",
                "arrow": None,
                "src_slot": slot,
            })
            continue

        # ── Top-level dispense ─────────────────────────────────────────
        m = _RE_DSP.match(line)
        if m:
            in_mix = False
            vol, well, lw, slot = m.groups()
            labware_map[slot] = lw
            arrow = (last_src_slot, slot) if last_src_slot and last_src_slot != slot else None
            active = [slot] + ([last_src_slot] if arrow else [])
            frames.append({
                "type": "dispense",
                "slots": active,
                "title": f"Dispense  {float(vol):.1f} µL",
                "detail": f"into {well}  ·  slot {slot}\n{SLOT_SHORT.get(lw, lw)}",
                "arrow": arrow,
            })
            continue

    return labware_map, frames


# ── Frame renderer ────────────────────────────────────────────────────────────

def render_frame(ax_deck, ax_info, ax_prog,
                 labware_map: dict, frames: list,
                 idx: int, protocol_name: str) -> None:
    for ax in (ax_deck, ax_info, ax_prog):
        ax.clear()

    frame = frames[idx]
    atype  = frame["type"]
    acolor = ACTION_COLOR.get(atype, "#2C3E50")
    active = set(frame["slots"])

    # ── Deck panel ────────────────────────────────────────────────────────────
    ax_deck.set_xlim(-0.58, 2.58)
    ax_deck.set_ylim(-0.62, 3.58)
    ax_deck.set_aspect("equal")
    ax_deck.axis("off")

    for ri, row in enumerate(FLEX_ROWS):
        for ci, col in enumerate(FLEX_COLS):
            slot = f"{row}{col}"
            x, y = float(ci), float(3 - ri)
            lw = labware_map.get(slot, "")
            is_active = slot in active

            fc    = _lw_color(lw, is_active) if lw else ("#D5D8DC" if is_active else "#EAECEE")
            ec    = acolor if is_active else "#BDC3C7"
            lw_   = 2.8 if is_active else 0.9
            alpha = 1.0 if (is_active or lw) else 0.5

            rect = mpatches.FancyBboxPatch(
                (x - 0.46, y - 0.46), 0.92, 0.92,
                boxstyle="round,pad=0.06",
                facecolor=fc, edgecolor=ec, linewidth=lw_, alpha=alpha,
            )
            ax_deck.add_patch(rect)

            # Slot label
            ax_deck.text(x - 0.40, y + 0.37, slot,
                         fontsize=7, color="#717D7E" if not is_active else "white",
                         va="top", ha="left", fontweight="bold", alpha=alpha)

            # Labware name
            short = SLOT_SHORT.get(lw, "")
            if short:
                ax_deck.text(x, y - 0.04, short,
                             fontsize=7.5, ha="center", va="center",
                             multialignment="center",
                             color="white" if is_active else "#1A252F",
                             fontweight="bold" if is_active else "normal",
                             alpha=alpha)

    # Transfer arrow
    if frame.get("arrow"):
        sx, sy = _slot_xy(frame["arrow"][0])
        dx, dy = _slot_xy(frame["arrow"][1])
        ax_deck.annotate(
            "",
            xy=(dx, dy), xytext=(sx, sy),
            arrowprops=dict(
                arrowstyle="-|>",
                color=acolor,
                lw=2.2,
                mutation_scale=18,
                connectionstyle="arc3,rad=0.3",
            ),
            zorder=15,
        )

    # ── Info panel ────────────────────────────────────────────────────────────
    ax_info.set_xlim(0, 1)
    ax_info.set_ylim(0, 1)
    ax_info.axis("off")

    # Colored bar on left edge
    bar = mpatches.FancyBboxPatch(
        (0.0, 0.0), 0.045, 1.0,
        boxstyle="square,pad=0",
        facecolor=acolor, edgecolor="none",
    )
    ax_info.add_patch(bar)

    # Icon + action label
    icon_text = ACTION_ICON.get(atype, atype)
    ax_info.text(0.10, 0.88, icon_text,
                 fontsize=15, color=acolor,
                 va="top", ha="left", fontweight="bold")

    # Title (bold)
    ax_info.text(0.10, 0.70, frame["title"],
                 fontsize=13, color="#1A252F",
                 va="top", ha="left", fontweight="bold")

    # Detail lines
    if frame.get("detail"):
        ax_info.text(0.10, 0.50, frame["detail"],
                     fontsize=10.5, color="#5D6D7E",
                     va="top", ha="left", linespacing=1.7)

    # Divider
    ax_info.plot([0.07, 0.97], [0.16, 0.16], color="#D5D8DC", lw=1)

    # Step counter
    ax_info.text(0.10, 0.09,
                 f"Step  {idx + 1}  /  {len(frames)}",
                 fontsize=9, color="#7F8C8D", va="center")
    ax_info.text(0.95, 0.09, protocol_name,
                 fontsize=8, color="#AEB6BF",
                 va="center", ha="right", style="italic")

    # ── Progress bar ──────────────────────────────────────────────────────────
    ax_prog.set_xlim(0, 1)
    ax_prog.set_ylim(0, 1)
    ax_prog.axis("off")

    progress = (idx + 1) / len(frames)
    ax_prog.barh(0.5, 1.0, height=1.0, color="#EAECEE", left=0, zorder=1)
    ax_prog.barh(0.5, progress, height=1.0, color=acolor, left=0, zorder=2, alpha=0.85)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Animated step-by-step visualizer for Opentrons Flex protocols."
    )
    parser.add_argument("protocol",       help="Protocol .py file path")
    parser.add_argument("--out",  default=None,  help="Output .gif path (default: <protocol>_animation.gif)")
    parser.add_argument("--fps",  type=float, default=1.5, help="Frames per second (default 1.5)")
    args = parser.parse_args()

    protocol_path = Path(args.protocol)
    if not protocol_path.exists():
        sys.exit(f"Protocol not found: {protocol_path}")

    # Simulate
    print(f"Simulating {protocol_path.name} ...")
    result = subprocess.run(
        ["opentrons_simulate", str(protocol_path)],
        capture_output=True, text=True,
    )
    if not result.stdout.strip():
        sys.exit(f"Simulation failed:\n{result.stderr[:600]}")

    labware_map, frames = parse_log(result.stdout)
    print(f"  {len(frames)} frames to render.")

    # Figure
    fig = plt.figure(figsize=(11, 5.5), facecolor="#FAFAFA")
    fig.suptitle(f"Protocol: {protocol_path.name}",
                 fontsize=12, fontweight="bold",
                 y=0.99, color="#2C3E50")

    gs = GridSpec(
        2, 2, figure=fig,
        width_ratios=[1.05, 1.35],
        height_ratios=[14, 1],
        hspace=0.06, wspace=0.06,
        left=0.03, right=0.98, top=0.94, bottom=0.03,
    )
    ax_deck = fig.add_subplot(gs[0, 0])
    ax_info = fig.add_subplot(gs[0, 1])
    ax_prog = fig.add_subplot(gs[1, :])

    def animate(i):
        render_frame(ax_deck, ax_info, ax_prog,
                     labware_map, frames, i, protocol_path.name)
        return []

    anim = FuncAnimation(
        fig, animate,
        frames=len(frames),
        interval=int(1000 / args.fps),
        blit=False,
        repeat=True,
    )

    out_path = args.out or str(
        protocol_path.with_stem(protocol_path.stem + "_animation").with_suffix(".gif")
    )
    print(f"  Writing GIF → {out_path}  (this may take a moment) ...")
    anim.save(out_path, writer=PillowWriter(fps=args.fps), dpi=130)
    print(f"Saved: {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
