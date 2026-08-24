"""
KiCad Sch AI Pin Assistant - Core Logic

AI-powered analysis of chip datasheet pin diagrams and generation
of KiCad schematic symbols (.kicad_sym format).

Author: HaydenHu
License: GPL-3.0
Version: 1.0.0
"""

import json
import os
import re
import sys
import textwrap
from datetime import datetime

# Ensure plugin directory is on sys.path for imports
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)


def _log_api(msg):
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] [API] {msg}\n")
    except Exception:
        pass


class PinData:
    """Represents a single pin extracted from AI analysis."""

    def __init__(
        self,
        number: str = "",
        name: str = "",
        etype: str = "passive",
        shape: str = "line",
        side: str = "left",
        index: int = 0,
    ):
        self.number = number
        self.name = name
        self.etype = etype
        self.shape = shape
        self.side = side
        self.index = index

    def __repr__(self):
        return f"PinData({self.number}: {self.name} [{self.etype}] @{self.side})"


def analyze_pin_diagram(
    api_key: str,
    model: str,
    endpoint: str,
    image_base64: str,
) -> list:
    """
    Send a pin diagram screenshot to the AI and extract structured pin data.

    Args:
        api_key: Agnes AI API key
        model: Model name (e.g. agnes-2.0-flash)
        endpoint: API endpoint URL
        image_base64: Base64-encoded PNG image data

    Returns:
        List of PinData objects extracted from the AI response
    """
    prompt = textwrap.dedent("""\
        Analyze this chip pinout/datasheet diagram image and extract all pin information.

        Return ONLY a valid JSON array of pin objects. Each pin object must have these fields:
        - "number": pin number as a string (e.g. "1", "A1", "VCC")
        - "name": pin name/function as a string (e.g. "VCC", "GND", "TX", "RESET")
        - "type": one of: "input", "output", "bidirectional", "tri_state", "passive", "power_in", "power_out", "open_collector", "open_emitter", "no_connect", "unspecified"
        - "side": which side of the chip the pin is on: "left", "right", "top", or "bottom"

        Guidelines:
        - Use "passive" for generic/unclear pins
        - Use "power_in" for all power pins: VCC, VDD, VIN, AVCC, GND, VSS, VEE etc.
        - Use "power_out" only for pins that explicitly output power (e.g. voltage regulator output)
        - Pins on the left side of the diagram map to "left"
        - Pins on the right side of the diagram map to "right"
        - Pins on top map to "top", bottom map to "bottom"
        - If the diagram shows a top-down pin view with pins arranged in a rectangle, determine sides accordingly
        - If pins are shown in a single column, default to "left"

        DO NOT include any markdown fences or explanatory text. Output ONLY the JSON array.
        Example output: [{"number":"1","name":"VCC","type":"power_in","side":"left"},{"number":"2","name":"GND","type":"power_in","side":"left"}]
    """)

    try:
        import requests
    except ImportError:
        raise ImportError(
            "The 'requests' package is required for AI analysis.\n"
            "Install it with: pip install requests"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        },
                    },
                ],
            }
        ],
    }

    _log_api("Sending POST to " + endpoint)
    _log_api("Model: " + model)
    _log_api("Image base64 length: " + str(len(image_base64)))
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=120)
    _log_api("Response status: " + str(resp.status_code))
    resp.raise_for_status()

    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    _log_api("AI response: " + content[:200])

    # Try to extract JSON from the response (in case AI wraps it in markdown)
    json_match = re.search(r"\[[\s\S]*\]", content.strip())
    if not json_match:
        raise ValueError(f"AI response does not contain a JSON array:\n{content[:500]}")

    pins_data = json.loads(json_match.group(0))

    pins = []
    for i, p in enumerate(pins_data):
        pins.append(PinData(
            number=str(p.get("number", "")),
            name=str(p.get("name", "")),
            etype=str(p.get("type", "passive")),
            shape="line",
            side=str(p.get("side", "left")),
            index=i,
        ))

    return pins


# === KiCad Symbol S-Expression Generator ===

# KiCad Symbol Editor default grid: 50 mil = 1.27 mm
GRID_MM = 1.27


def _round_grid(value_mm: float) -> float:
    """Round a value to the nearest grid unit (1.27mm)."""
    return round(value_mm / GRID_MM) * GRID_MM


def _mm_to_kicad(mm: float) -> str:
    """Convert mm to KiCad internal units string, rounded to grid."""
    g = _round_grid(mm)
    # Strip trailing zeros but keep at least one decimal
    s = f"{g:.4f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def _escape_sym_text(text: str) -> str:
    """Escape special characters in KiCad S-expression text."""
    # Escape backslash, quotes, and braces
    text = text.replace("\\", "\\\\")
    text = text.replace('"', '\\"')
    return text


def generate_kicad_symbol(
    sym_name: str,
    ref_prefix: str,
    pins: list,
    pin_length_mm: float = 2.54,
    pin_spacing_mm: float = 2.54,
    show_pin_numbers: bool = True,
    show_pin_names: bool = True,
) -> str:
    """
    Generate a KiCad .kicad_sym file content from pin data.

    The generated symbol follows KiCad 10.x format with a single unit (0)
    and a single body style (1).

    Args:
        sym_name: Symbol name (e.g. "STM32F103C8T6")
        ref_prefix: Reference designator prefix (e.g. "U", "IC")
        pins: List of PinData objects
        pin_length_mm: Pin length in mm
        pin_spacing_mm: Vertical spacing between pins in mm
        show_pin_numbers: Whether to show pin numbers
        show_pin_names: Whether to show pin names

    Returns:
        Complete .kicad_sym file content as a string
    """
    # Separate pins by side
    left_pins = [p for p in pins if p.side == "left"]
    right_pins = [p for p in pins if p.side == "right"]
    top_pins = [p for p in pins if p.side == "top"]
    bottom_pins = [p for p in pins if p.side == "bottom"]

    # Calculate body dimensions
    left_height = (len(left_pins) - 1) * pin_spacing_mm
    right_height = (len(right_pins) - 1) * pin_spacing_mm
    body_height = max(left_height, right_height, 2.54)

    top_width = (len(top_pins) - 1) * pin_spacing_mm
    bottom_width = (len(bottom_pins) - 1) * pin_spacing_mm
    body_width = max(top_width, bottom_width, 2.54)

    # Add margin: at least one pin_spacing extra, minimum 5.08mm
    body_height = max(body_height + pin_spacing_mm, 5.08)
    body_width = max(body_width + pin_spacing_mm, 5.08)

    half_w = body_width / 2.0
    half_h = body_height / 2.0
    pin_len = pin_length_mm

    lines = []
    _I = lambda n, s: (" " * n) + s

    # === Library header ===
    lines.append("(kicad_symbol_lib")
    lines.append(_I(4, "(version 20251024)"))
    lines.append(_I(4, '(generator "kicad_symbol_editor")'))
    lines.append(_I(4, '(generator_version "10.0")'))

    # === Main symbol entry ===
    lines.append(_I(4, f'(symbol "{_escape_sym_text(sym_name)}"'))

    # Pin settings
    lines.append(_I(8, "(pin_names"))
    lines.append(_I(12, "(offset 1.016)"))
    if not show_pin_names:
        lines.append(_I(12, "(hide yes)"))
    lines.append(_I(8, ")"))
    lines.append(_I(8, "(pin_numbers"))
    if not show_pin_numbers:
        lines.append(_I(12, "(hide yes)"))
    else:
        lines.append(_I(12, "(size 1.27 1.27)"))
    lines.append(_I(8, ")"))

    lines.append(_I(8, "(exclude_from_sim no)"))
    lines.append(_I(8, "(in_bom yes)"))
    lines.append(_I(8, "(on_board yes)"))
    lines.append(_I(8, "(in_pos_files yes)"))
    lines.append(_I(8, "(duplicate_pin_numbers_are_jumpers no)"))

    # Properties
    ref_y = half_h + 2.54
    val_y = -(half_h + 2.54)

    lines.append(_I(8, f'(property "Reference" "{_escape_sym_text(ref_prefix)}"'))
    lines.append(_I(12, f"(at 0 {_mm_to_kicad(ref_y)} 0)"))
    lines.append(_I(12, "(show_name no)"))
    lines.append(_I(12, "(do_not_autoplace no)"))
    lines.append(_I(12, "(effects (font (size 1.27 1.27))))"))
    lines.append(_I(8, ")"))

    lines.append(_I(8, f'(property "Value" "{_escape_sym_text(sym_name)}"'))
    lines.append(_I(12, f"(at 0 {_mm_to_kicad(val_y)} 0)"))
    lines.append(_I(12, "(show_name no)"))
    lines.append(_I(12, "(do_not_autoplace no)"))
    lines.append(_I(12, "(effects (font (size 1.27 1.27))))"))
    lines.append(_I(8, ")"))

    lines.append(_I(8, '(property "Footprint" ""'))
    lines.append(_I(12, "(at 0 0 0)"))
    lines.append(_I(12, "(show_name no)"))
    lines.append(_I(12, "(do_not_autoplace no)"))
    lines.append(_I(12, "(hide yes)"))
    lines.append(_I(12, "(effects (font (size 1.27 1.27))))"))
    lines.append(_I(8, ")"))

    lines.append(_I(8, '(property "Datasheet" ""'))
    lines.append(_I(12, "(at 0 0 0)"))
    lines.append(_I(12, "(show_name no)"))
    lines.append(_I(12, "(do_not_autoplace no)"))
    lines.append(_I(12, "(hide yes)"))
    lines.append(_I(12, "(effects (font (size 1.27 1.27))))"))
    lines.append(_I(8, ")"))

    desc = f"AI-generated symbol for {sym_name}"
    lines.append(_I(8, f'(property "Description" "{_escape_sym_text(desc)}"'))
    lines.append(_I(12, "(at 0 0 0)"))
    lines.append(_I(12, "(show_name no)"))
    lines.append(_I(12, "(do_not_autoplace no)"))
    lines.append(_I(12, "(hide yes)"))
    lines.append(_I(12, "(effects (font (size 1.27 1.27))))"))
    lines.append(_I(8, ")"))

    # === Unit sub-symbol (body + pins) ===
    sub_name = f"{sym_name}_0_1"
    lines.append(_I(8, f'(symbol "{_escape_sym_text(sub_name)}"'))

    # Rectangle body
    lines.append(_I(12, "(rectangle"))
    lines.append(_I(16, f"(start {_mm_to_kicad(-half_w)} {_mm_to_kicad(half_h)})"))
    lines.append(_I(16, f"(end {_mm_to_kicad(half_w)} {_mm_to_kicad(-half_h)})"))
    lines.append(_I(16, "(stroke (width 0.254) (type default))"))
    lines.append(_I(16, "(fill (type background))"))
    lines.append(_I(12, ")"))

    # Helper: generate a pin
    VALID_ETYPES = {
        "input", "output", "bidirectional", "tri_state", "passive",
        "free", "unspecified", "power_in", "power_out",
        "open_collector", "open_emitter", "no_connect",
    }
    VALID_SHAPES = {
        "line", "inverted", "clock", "inverted_clock",
        "input_low", "clock_low", "output_low",
        "edge_clock_high", "non_logic",
    }

    def _pin(pin, pos_x_mm, pos_y_mm, rotation):
        etype = pin.etype if pin.etype in VALID_ETYPES else "passive"
        shape = pin.shape if pin.shape in VALID_SHAPES else "line"
        pl = []
        pl.append(_I(12, f"(pin {etype} {shape}"))
        pl.append(_I(16, f"(at {_mm_to_kicad(pos_x_mm)} {_mm_to_kicad(pos_y_mm)} {rotation})"))
        pl.append(_I(16, f"(length {_mm_to_kicad(pin_len)})"))
        pl.append(_I(16, f'(name "{_escape_sym_text(pin.name)}"'))
        pl.append(_I(20, "(effects (font (size 1.27 1.27)))"))
        pl.append(_I(16, ")"))
        pl.append(_I(16, f'(number "{_escape_sym_text(pin.number)}"'))
        pl.append(_I(20, "(effects (font (size 1.27 1.27)))"))
        pl.append(_I(16, ")"))
        pl.append(_I(12, ")"))
        return "\n".join(pl)

    # Left side pins (rotation 0 = pointing right from left edge)
    for i, pin in enumerate(left_pins):
        y = half_h - pin_spacing_mm * i
        x = -(half_w + pin_len)
        lines.append(_pin(pin, x, y, 0))

    # Right side pins (rotation 180 = pointing left from right edge)
    for i, pin in enumerate(right_pins):
        y = half_h - pin_spacing_mm * i
        x = half_w + pin_len
        lines.append(_pin(pin, x, y, 180))

    # Top side pins (rotation 270 = pointing down from top edge)
    for i, pin in enumerate(top_pins):
        x = -half_w + pin_spacing_mm * i
        y = half_h + pin_len
        lines.append(_pin(pin, x, y, 270))

    # Bottom side pins (rotation 90 = pointing up from bottom edge)
    for i, pin in enumerate(bottom_pins):
        x = -half_w + pin_spacing_mm * i
        y = -(half_h + pin_len)
        lines.append(_pin(pin, x, y, 90))

    # Close sub-symbol
    lines.append(_I(8, ")"))

    # Close main symbol
    lines.append(_I(4, ")"))

    # Close library
    lines.append(")")

    return "\n".join(lines) + "\n"


def generate_symbol_items(
    sym_name: str = "CHIP",
    ref_prefix: str = "U",
    pins: list | None = None,
    pin_length_mm: float = 2.54,
    pin_spacing_mm: float = 2.54,
) -> str:
    """
    Generate a complete symbol S-expression block that can be pasted
    directly into KiCad's Symbol Editor (Edit -> Paste) or via Ctrl+V.

    The output is a full symbol definition with two sub-symbols:
    - _0_1 : empty body rectangle (for single-unit symbols)
    - _1_1 : pin layout on all four sides

    Args:
        sym_name: Symbol name
        ref_prefix: Reference prefix (e.g. "U", "IC")
        pins: List of PinData objects
        pin_length_mm: Pin length in mm
        pin_spacing_mm: Vertical pin spacing in mm

    Returns:
        S-expression symbol block ready for clipboard paste
    """
    if pins is None:
        pins = []

    left_pins = [p for p in pins if p.side == "left"]
    right_pins = [p for p in pins if p.side == "right"]
    top_pins = [p for p in pins if p.side == "top"]
    bottom_pins = [p for p in pins if p.side == "bottom"]

    # Estimate text width: KiCad font ~1.1mm per character at 1.27 size
    FONT_CHAR_WIDTH = 1.1

    def _max_text_width(pin_list):
        return max((len(p.name) * FONT_CHAR_WIDTH for p in pin_list), default=0)

    # Body sizing based on pin count, all rounded to grid
    left_n = len(left_pins); right_n = len(right_pins)
    top_n = len(top_pins); bottom_n = len(bottom_pins)

    # Vertical extent from left/right pins (spaced by GRID_MM)
    body_span_y = max(left_n, right_n) * pin_spacing_mm
    # Horizontal extent from top/bottom pins
    body_span_x = max(top_n, bottom_n) * pin_spacing_mm

    # Add room for pin names + margins, all grid-rounded
    max_left_name_w = _max_text_width(left_pins)
    max_right_name_w = _max_text_width(right_pins)
    max_top_name_h = _max_text_width(top_pins)
    max_bottom_name_h = _max_text_width(bottom_pins)

    total_width = max(body_span_x, 5.08) + max_left_name_w + max_right_name_w + 5.08
    total_height = max(body_span_y, 5.08) + max_top_name_h + max_bottom_name_h + 5.08

    # Round everything to grid
    half_w = _round_grid(total_width / 2.0)
    half_h = _round_grid(total_height / 2.0)
    pin_len = _round_grid(pin_length_mm)
    pin_spacing = _round_grid(pin_spacing_mm)

    VALID_ETYPES = {
        "input", "output", "bidirectional", "tri_state", "passive",
        "free", "unspecified", "power_in", "power_out",
        "open_collector", "open_emitter", "no_connect",
    }
    VALID_SHAPES = {
        "line", "inverted", "clock", "inverted_clock",
        "input_low", "clock_low", "output_low",
        "edge_clock_high", "non_logic",
    }

    L = lambda n, t: (" " * (4 * n)) + t

    lines = []

    # ── Outer symbol wrapper ──
    escaped_name = _escape_sym_text(sym_name)
    lines.append('(symbol "{}"'.format(escaped_name))
    lines.append(L(1, "(exclude_from_sim no)"))
    lines.append(L(1, "(in_bom yes)"))
    lines.append(L(1, "(on_board yes)"))
    lines.append(L(1, "(in_pos_files yes)"))
    lines.append(L(1, "(duplicate_pin_numbers_are_jumpers no)"))

    # ── Properties ──
    ref_x = -half_w - pin_len - 2.54
    ref_y = half_h + 2.54
    _add_property(lines, L, ref_x, ref_y, 0, "Reference", ref_prefix, True, "left")

    val_x = half_w + pin_len + 2.54
    val_y = -(half_h + 2.54)
    _add_property(lines, L, val_x, val_y, 0, "Value", escaped_name, False, "right")

    _add_hidden_property(lines, L, 0, 0, "Footprint", "")
    _add_hidden_property(lines, L, 0, 0, "Datasheet", "")
    _add_hidden_property(lines, L, 0, 0, "Description", "")

    # ── Sub-symbol 1: empty rectangle (unit 0, style 1) ──
    sub1_name = "{}_0_1".format(escaped_name)
    lines.append(L(1, '(symbol "{}"'.format(sub1_name)))
    lines.append(L(2, "(rectangle"))
    lines.append(L(3, "(start {} {})".format(_mm_to_kicad(-half_w), _mm_to_kicad(half_h))))
    lines.append(L(3, "(end {} {})".format(_mm_to_kicad(half_w), _mm_to_kicad(-half_h))))
    lines.append(L(3, "(stroke (width 0) (type default))"))
    lines.append(L(3, "(fill (type background))"))
    lines.append(L(2, ")"))
    lines.append(L(1, ")"))

    # ── Sub-symbol 2: body + pins (unit 1, style 1) ──
    sub2_name = "{}_1_1".format(escaped_name)
    lines.append(L(1, '(symbol "{}"'.format(sub2_name)))

    lines.append(L(2, "(rectangle"))
    lines.append(L(3, "(start {} {})".format(_mm_to_kicad(-half_w), _mm_to_kicad(half_h))))
    lines.append(L(3, "(end {} {})".format(_mm_to_kicad(half_w), _mm_to_kicad(-half_h))))
    lines.append(L(3, "(stroke (width 0) (type default))"))
    lines.append(L(3, "(fill (type background))"))
    lines.append(L(2, ")"))

    # Helper to add a pin
    def _add_pin_lines(name_str, number_str, at_x, at_y, rot, etype, shape):
        lines.append(L(2, "(pin {} {}".format(etype, shape)))
        lines.append(L(3, "(at {} {} {})".format(_mm_to_kicad(at_x), _mm_to_kicad(at_y), rot)))
        lines.append(L(3, "(length {})".format(_mm_to_kicad(pin_len))))
        ename = _escape_sym_text(name_str)
        lines.append(L(3, '(name "{}"'.format(ename)))
        lines.append(L(4, "(effects"))
        lines.append(L(5, "(font (size 1.27 1.27))"))
        lines.append(L(4, ")"))
        lines.append(L(3, ")"))
        enumber = _escape_sym_text(number_str)
        lines.append(L(3, '(number "{}"'.format(enumber)))
        lines.append(L(4, "(effects"))
        lines.append(L(5, "(font (size 1.27 1.27))"))
        lines.append(L(4, ")"))
        lines.append(L(3, ")"))
        lines.append(L(2, ")"))

    # Pin placement positions (all grid-rounded via math above)
    left_n = len(left_pins); right_n = len(right_pins)
    top_n = len(top_pins); bottom_n = len(bottom_pins)

    # Left side pins (rotation 0 = points right) — centered vertically
    for i, pin in enumerate(left_pins):
        center_y = ((left_n - 1) / 2.0) * pin_spacing
        y = center_y - pin_spacing * i
        x = -(half_w + pin_len)
        etype = pin.etype if pin.etype in VALID_ETYPES else "passive"
        shape = pin.shape if pin.shape in VALID_SHAPES else "line"
        _add_pin_lines(pin.name, pin.number, x, y, 0, etype, shape)

    # Right side pins (rotation 180 = points left) — centered vertically
    for i, pin in enumerate(right_pins):
        center_y = ((right_n - 1) / 2.0) * pin_spacing
        y = center_y - pin_spacing * i
        x = half_w + pin_len
        etype = pin.etype if pin.etype in VALID_ETYPES else "passive"
        shape = pin.shape if pin.shape in VALID_SHAPES else "line"
        _add_pin_lines(pin.name, pin.number, x, y, 180, etype, shape)

    # Top side pins (rotation 270 = points down) — centered horizontally
    for i, pin in enumerate(top_pins):
        center_x = ((top_n - 1) / 2.0) * pin_spacing
        x = center_x - pin_spacing * i
        y = half_h + pin_len
        etype = pin.etype if pin.etype in VALID_ETYPES else "passive"
        shape = pin.shape if pin.shape in VALID_SHAPES else "line"
        _add_pin_lines(pin.name, pin.number, x, y, 270, etype, shape)

    # Bottom side pins (rotation 90 = points up) — centered horizontally
    for i, pin in enumerate(bottom_pins):
        center_x = ((bottom_n - 1) / 2.0) * pin_spacing
        x = center_x - pin_spacing * i
        y = -(half_h + pin_len)
        etype = pin.etype if pin.etype in VALID_ETYPES else "passive"
        shape = pin.shape if pin.shape in VALID_SHAPES else "line"
        _add_pin_lines(pin.name, pin.number, x, y, 90, etype, shape)

    lines.append(L(1, ")"))

    # ── Footer ──
    lines.append(L(1, "(embedded_fonts no)"))
    lines.append(")")

    return "\n".join(lines) + "\n"


def _add_property(lines, L, x_mm, y_mm, rot, prop_name, value, show_name, justify):
    """Helper to add a visible property."""
    JUSTIFY_MAP = {"left": "left", "right": "right", "center": "center"}
    js = JUSTIFY_MAP.get(justify, "")
    escaped_val = _escape_sym_text(value)
    lines.append(L(1, '(property "{}" "{}"'.format(prop_name, escaped_val)))
    lines.append(L(2, "(at {} {} {})".format(_mm_to_kicad(x_mm), _mm_to_kicad(y_mm), rot)))
    lines.append(L(2, "(show_name {})".format("yes" if show_name else "no")))
    lines.append(L(2, "(do_not_autoplace no)"))
    lines.append(L(2, "(effects"))
    lines.append(L(3, "(font (size 1.27 1.27))"))
    if js:
        lines.append(L(3, "(justify {})".format(js)))
    lines.append(L(2, ")"))
    lines.append(L(1, ")"))


def _add_hidden_property(lines, L, x_mm, y_mm, prop_name, value):
    """Helper to add a hidden property."""
    escaped_val = _escape_sym_text(value)
    lines.append(L(1, '(property "{}" "{}"'.format(prop_name, escaped_val)))
    lines.append(L(2, "(at {} {} 0)".format(_mm_to_kicad(x_mm), _mm_to_kicad(y_mm))))
    lines.append(L(2, "(show_name no)"))
    lines.append(L(2, "(do_not_autoplace no)"))
    lines.append(L(2, "(hide yes)"))
    lines.append(L(2, "(effects"))
    lines.append(L(3, "(font (size 1.27 1.27))"))
    lines.append(L(2, ")"))
    lines.append(L(1, ")"))


# === Plugin entry point ===

def main():
    """
    Plugin entry point called by KiCad IPC API.

    Launches the AI Pin Assistant GUI dialog.
    """
    import os
    import sys
    import traceback

    try:
        _main()
    except Exception:
        msg = f"AI Pin Assistant Error:\n\n{traceback.format_exc()}"
        print(msg, file=sys.stderr)
        try:
            import wx
            if not wx.GetApp():
                _ = wx.App()
            wx.MessageBox(msg, "AI Pin Assistant Error", wx.OK | wx.ICON_ERROR)
        except Exception:
            pass
        sys.exit(1)


def _main():
    """Internal main: set up wx App and show the dialog."""
    import os
    import wx

    # Ensure wx App exists (KiCad provides one, but plugin may run standalone)
    if not wx.GetApp():
        _ = wx.App()

    from sch_ai_assistant_gui import SchAiAssistantDialog

    plugin_dir = os.path.dirname(os.path.abspath(__file__))

    dialog = SchAiAssistantDialog(None, plugin_dir)
    dialog.ShowModal()
    dialog.Destroy()


if __name__ == "__main__":
    main()
