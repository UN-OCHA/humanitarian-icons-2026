#!/usr/bin/env python3
"""
generate-grid.py — Generate a master SVG grid of all OCHA humanitarian icons.

Reads metadata.json + individual SVG files and produces a single, flat SVG
with all icons organized by family. Every icon's vector paths are embedded
directly (no <image>, <use>, or external references) so the output opens in
Adobe Illustrator with fully editable paths.

No external dependencies — pure Python standard library.
"""

import json
import math
import os
import re
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ICON_SIZE = 48          # max icon render size (fit within this box)
CELL_WIDTH = 80         # total cell width
CELL_HEIGHT = 80        # total cell height (icon + label + spacing)
COLS = 8                # icons per row
HEADER_HEIGHT = 40      # family header row height
LOGO_HEIGHT = 30        # OCHA logo height at top
FONT = "Roboto, Arial, Helvetica, sans-serif"
ICON_COLOR = "#009edb"
LABEL_COLOR = "#4a4a4a"
HEADER_BG = "#f0f0f0"
HEADER_TEXT_COLOR = "#333333"
PAGE_MARGIN = 20

# Derived
GRID_WIDTH = COLS * CELL_WIDTH
TOTAL_WIDTH = GRID_WIDTH + 2 * PAGE_MARGIN

# ---------------------------------------------------------------------------
# Paths (relative to repo root)
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
METADATA_PATH = os.path.join(REPO_ROOT, "metadata.json")
SVG_DIR = os.path.join(REPO_ROOT, "svg")
LOGO_PATH = os.path.join(REPO_ROOT, "assets", "OCHA_logo_horizontal_blue.svg")
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "Humanitarian_icons_complete_library.svg")


# ---------------------------------------------------------------------------
# SVG helper: parse viewBox
# ---------------------------------------------------------------------------
def parse_viewbox(svg_text):
    """Return (min_x, min_y, width, height) from the viewBox attribute."""
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_text)
    if not m:
        return (0, 0, 48, 48)
    parts = m.group(1).split()
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


# ---------------------------------------------------------------------------
# SVG helper: extract inner content and clean it
# ---------------------------------------------------------------------------
def extract_svg_inner(svg_text):
    """
    Extract the content inside the root <svg> element, stripping:
      - <?xml ...?> declarations
      - <!-- comments -->
      - <defs>...</defs> blocks
      - <style>...</style> blocks
      - <title>...</title> blocks
    Returns the cleaned inner SVG markup string.
    """
    # Remove XML declaration
    text = re.sub(r'<\?xml[^?]*\?>', '', svg_text)
    # Remove comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # Extract content between <svg ...> and </svg>
    m = re.search(r'<svg[^>]*>(.*)</svg>', text, re.DOTALL)
    if not m:
        return ""
    inner = m.group(1)

    # Strip <defs>...</defs>
    inner = re.sub(r'<defs>.*?</defs>', '', inner, flags=re.DOTALL)
    inner = re.sub(r'<defs\s[^>]*>.*?</defs>', '', inner, flags=re.DOTALL)
    # Strip <style>...</style>
    inner = re.sub(r'<style[^>]*>.*?</style>', '', inner, flags=re.DOTALL)
    # Strip <title>...</title>
    inner = re.sub(r'<title>.*?</title>', '', inner, flags=re.DOTALL)

    return inner.strip()


# ---------------------------------------------------------------------------
# SVG helper: resolve CSS classes to direct fill attributes
# ---------------------------------------------------------------------------

# Shape element names that should get a fill
SHAPE_ELEMENTS = {'path', 'circle', 'rect', 'polygon', 'ellipse', 'line', 'polyline'}


def clean_svg_content(inner_svg, fill_color=None):
    """
    Process extracted SVG inner content:
      1. Remove all class="..." attributes
      2. Remove style="..." attributes (they only contain fill/stroke-width from CSS)
      3. Add fill="<color>" to shape elements that don't already have one
      4. Preserve fill-rule="evenodd" if it was in the CSS class
    """
    if fill_color is None:
        fill_color = ICON_COLOR

    # Detect if fill-rule:evenodd is used for any class
    has_evenodd = 'fill-rule:evenodd' in inner_svg or 'fill-rule: evenodd' in inner_svg

    # Remove class attributes
    result = re.sub(r'\s+class="[^"]*"', '', inner_svg)

    # Remove style attributes that just contain fill/stroke-width declarations
    # These come from the CSS classes and are not needed once we add direct fill
    result = re.sub(r'\s+style="[^"]*"', '', result)

    # For each shape element, ensure it has a direct fill attribute
    def add_fill_to_element(match):
        tag_text = match.group(0)
        # Extract element name
        elem_m = re.match(r'<(\w+)', tag_text)
        if not elem_m:
            return tag_text
        elem_name = elem_m.group(1)

        if elem_name not in SHAPE_ELEMENTS:
            return tag_text

        # Skip if already has explicit fill attribute
        if re.search(r'\bfill\s*=', tag_text):
            return tag_text

        # Insert fill attribute after the element name
        return tag_text.replace(
            '<' + elem_name,
            '<' + elem_name + ' fill="' + fill_color + '"',
            1
        )

    # Match opening tags (self-closing or not)
    result = re.sub(r'<(\w+)(?:\s[^>]*)?\s*/?>', add_fill_to_element, result)

    return result


def clean_svg_content_with_evenodd(inner_svg, style_text, fill_color=None):
    """
    Enhanced version that also handles fill-rule:evenodd from CSS classes.
    Parses the <style> to know which classes have evenodd, then applies
    fill-rule="evenodd" as a direct attribute on those elements.
    """
    if fill_color is None:
        fill_color = ICON_COLOR

    # Parse which CSS classes have fill-rule:evenodd
    evenodd_classes = set()
    if style_text:
        # Match patterns like .cls-1{...fill-rule:evenodd...}
        for m in re.finditer(r'\.([\w-]+)\s*\{[^}]*fill-rule\s*:\s*evenodd[^}]*\}', style_text):
            evenodd_classes.add(m.group(1))

    # Build a map: for each element, check if its class is in evenodd_classes
    def process_element(match):
        tag_text = match.group(0)
        elem_m = re.match(r'<(\w+)', tag_text)
        if not elem_m:
            return tag_text
        elem_name = elem_m.group(1)

        # Check if this element's class is an evenodd class
        needs_evenodd = False
        cls_m = re.search(r'class="([^"]*)"', tag_text)
        if cls_m and evenodd_classes:
            for cls in cls_m.group(1).split():
                if cls in evenodd_classes:
                    needs_evenodd = True
                    break

        # Remove class attribute
        tag_text = re.sub(r'\s+class="[^"]*"', '', tag_text)
        # Remove style attribute
        tag_text = re.sub(r'\s+style="[^"]*"', '', tag_text)

        if elem_name not in SHAPE_ELEMENTS:
            return tag_text

        # Add fill if not present
        if not re.search(r'\bfill\s*=', tag_text):
            tag_text = tag_text.replace(
                '<' + elem_name,
                '<' + elem_name + ' fill="' + fill_color + '"',
                1
            )

        # Add fill-rule if needed
        if needs_evenodd and 'fill-rule' not in tag_text:
            tag_text = tag_text.replace(
                '<' + elem_name,
                '<' + elem_name + ' fill-rule="evenodd"',
                1
            )

        return tag_text

    result = re.sub(r'<(\w+)(?:\s[^>]*)?\s*/?>', process_element, inner_svg)
    return result


# ---------------------------------------------------------------------------
# Process a single icon SVG file
# ---------------------------------------------------------------------------
def process_icon_svg(svg_path, fill_color=None):
    """
    Read an icon SVG file and return:
      (viewbox_w, viewbox_h, cleaned_inner_svg)
    or None if the file can't be processed.
    """
    if fill_color is None:
        fill_color = ICON_COLOR

    with open(svg_path, 'r', encoding='utf-8') as f:
        svg_text = f.read()

    _, _, vb_w, vb_h = parse_viewbox(svg_text)

    # Extract the <style> content before stripping (for evenodd detection)
    style_m = re.search(r'<style[^>]*>(.*?)</style>', svg_text, re.DOTALL)
    style_text = style_m.group(1) if style_m else ""

    # Extract inner content
    inner = extract_svg_inner(svg_text)
    if not inner:
        return None

    # Clean: resolve classes to direct fill attributes
    if 'fill-rule' in style_text:
        cleaned = clean_svg_content_with_evenodd(inner, style_text, fill_color)
    else:
        cleaned = clean_svg_content(inner, fill_color)

    return (vb_w, vb_h, cleaned)


# ---------------------------------------------------------------------------
# Process the OCHA logo SVG
# ---------------------------------------------------------------------------
def process_logo_svg(logo_path, target_height):
    """
    Read the OCHA logo SVG and return:
      (rendered_width, rendered_height, svg_group_string)
    The group is pre-scaled and ready to place.
    """
    with open(logo_path, 'r', encoding='utf-8') as f:
        svg_text = f.read()

    _, _, vb_w, vb_h = parse_viewbox(svg_text)
    inner = extract_svg_inner(svg_text)

    # Clean class/style attributes from the logo too
    style_m = re.search(r'<style[^>]*>(.*?)</style>', svg_text, re.DOTALL)
    style_text = style_m.group(1) if style_m else ""
    if 'fill-rule' in style_text:
        cleaned = clean_svg_content_with_evenodd(inner, style_text, ICON_COLOR)
    else:
        cleaned = clean_svg_content(inner, ICON_COLOR)

    scale = target_height / vb_h if vb_h > 0 else 1
    rendered_w = vb_w * scale

    return (rendered_w, target_height, cleaned, vb_w, vb_h, scale)


# ---------------------------------------------------------------------------
# XML/SVG escaping
# ---------------------------------------------------------------------------
def xml_escape(text):
    """Escape text for use inside XML attributes or text nodes."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------
def main():
    # Load metadata
    with open(METADATA_PATH, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    families_order = metadata['families']
    icons_data = metadata['icons']

    # Group icons by family
    families = {}
    for icon_key, icon_info in icons_data.items():
        family = icon_info.get('family', 'Other')
        if family not in families:
            families[family] = []
        families[family].append((icon_key, icon_info))

    # Sort icons within each family alphabetically by display name
    for family in families:
        families[family].sort(key=lambda x: x[1]['name'].lower())

    # -----------------------------------------------------------------------
    # Calculate total page height
    # -----------------------------------------------------------------------
    # Header area: logo + title + separator
    header_area_height = LOGO_HEIGHT + 20 + 1 + 15  # logo + gap + line + gap

    y_cursor = PAGE_MARGIN + header_area_height

    family_layouts = []
    for family_name in families_order:
        if family_name not in families:
            continue
        icon_list = families[family_name]
        num_icons = len(icon_list)
        num_rows = math.ceil(num_icons / COLS)
        grid_height = num_rows * CELL_HEIGHT

        family_layouts.append({
            'name': family_name,
            'icons': icon_list,
            'y': y_cursor,
            'header_y': y_cursor,
            'grid_y': y_cursor + HEADER_HEIGHT,
            'num_rows': num_rows,
        })

        y_cursor += HEADER_HEIGHT + grid_height + 10  # 10px gap between families

    total_height = y_cursor + PAGE_MARGIN

    # -----------------------------------------------------------------------
    # Build SVG output
    # -----------------------------------------------------------------------
    svg_parts = []

    # SVG root element
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'version="1.1" '
        f'width="{TOTAL_WIDTH}" height="{total_height}" '
        f'viewBox="0 0 {TOTAL_WIDTH} {total_height}">'
    )

    # Background
    svg_parts.append(
        f'<rect x="0" y="0" width="{TOTAL_WIDTH}" height="{total_height}" fill="#ffffff"/>'
    )

    # -------------------------------------------------------------------
    # Header area: OCHA logo + title
    # -------------------------------------------------------------------
    logo_x = PAGE_MARGIN
    logo_y = PAGE_MARGIN

    try:
        logo_rw, logo_rh, logo_inner, logo_vbw, logo_vbh, logo_scale = \
            process_logo_svg(LOGO_PATH, LOGO_HEIGHT)
        svg_parts.append(
            f'<g transform="translate({logo_x},{logo_y}) scale({logo_scale:.6f})">'
        )
        svg_parts.append(logo_inner)
        svg_parts.append('</g>')
        title_x = logo_x + logo_rw + 15
    except Exception as e:
        print(f"  WARNING: Could not embed OCHA logo: {e}", file=sys.stderr)
        title_x = logo_x

    # Title text
    title_y = logo_y + LOGO_HEIGHT / 2 + 5
    svg_parts.append(
        f'<text x="{title_x}" y="{title_y}" '
        f'font-family="{FONT}" font-size="16" '
        f'fill="{HEADER_TEXT_COLOR}" '
        f'dominant-baseline="middle">'
        f'Humanitarian icons</text>'
    )

    # Separator line
    sep_y = PAGE_MARGIN + LOGO_HEIGHT + 10
    svg_parts.append(
        f'<line x1="{PAGE_MARGIN}" y1="{sep_y}" '
        f'x2="{TOTAL_WIDTH - PAGE_MARGIN}" y2="{sep_y}" '
        f'stroke="#cccccc" stroke-width="0.5"/>'
    )

    # -------------------------------------------------------------------
    # Icon grid by family
    # -------------------------------------------------------------------
    icons_embedded = 0
    icons_failed = 0

    for fam_layout in family_layouts:
        family_name = fam_layout['name']
        icon_list = fam_layout['icons']
        header_y = fam_layout['header_y']
        grid_y = fam_layout['grid_y']

        # Family header background
        svg_parts.append(
            f'<rect x="{PAGE_MARGIN}" y="{header_y}" '
            f'width="{GRID_WIDTH}" height="{HEADER_HEIGHT}" '
            f'fill="{HEADER_BG}" rx="3" ry="3"/>'
        )

        # Family header text
        text_y = header_y + HEADER_HEIGHT / 2
        svg_parts.append(
            f'<text x="{PAGE_MARGIN + 10}" y="{text_y}" '
            f'font-family="{FONT}" font-size="14" font-weight="bold" '
            f'fill="{HEADER_TEXT_COLOR}" '
            f'dominant-baseline="central">'
            f'{xml_escape(family_name)}</text>'
        )

        # Icon count badge
        svg_parts.append(
            f'<text x="{PAGE_MARGIN + GRID_WIDTH - 10}" y="{text_y}" '
            f'font-family="{FONT}" font-size="10" '
            f'fill="{LABEL_COLOR}" '
            f'dominant-baseline="central" text-anchor="end">'
            f'{len(icon_list)} icons</text>'
        )

        # Render each icon
        for idx, (icon_key, icon_info) in enumerate(icon_list):
            col = idx % COLS
            row = idx // COLS
            cell_x = PAGE_MARGIN + col * CELL_WIDTH
            cell_y = grid_y + row * CELL_HEIGHT

            # Center of the icon area within the cell
            icon_area_top = cell_y + 4  # small top padding
            label_y = cell_y + CELL_HEIGHT - 10  # label near bottom

            svg_file = os.path.join(SVG_DIR, icon_key + ".svg")
            if not os.path.isfile(svg_file):
                icons_failed += 1
                print(f"  WARNING: SVG not found for '{icon_key}'", file=sys.stderr)
                continue

            result = process_icon_svg(svg_file)
            if result is None:
                icons_failed += 1
                print(f"  WARNING: Could not process '{icon_key}'", file=sys.stderr)
                continue

            vb_w, vb_h, cleaned_inner = result

            # Calculate scale to fit within ICON_SIZE x ICON_SIZE
            if vb_w <= 0 or vb_h <= 0:
                scale = 1.0
            else:
                scale_x = ICON_SIZE / vb_w
                scale_y = ICON_SIZE / vb_h
                scale = min(scale_x, scale_y)

            rendered_w = vb_w * scale
            rendered_h = vb_h * scale

            # Center the icon horizontally in the cell, position at top of icon area
            icon_x = cell_x + (CELL_WIDTH - rendered_w) / 2
            icon_y = icon_area_top + (ICON_SIZE - rendered_h) / 2

            # Wrap in a group with translate + scale
            svg_parts.append(
                f'<g transform="translate({icon_x:.2f},{icon_y:.2f}) scale({scale:.6f})">'
            )
            svg_parts.append(cleaned_inner)
            svg_parts.append('</g>')

            # Label below icon
            display_name = icon_info.get('name', icon_key)
            # Truncate long names for display
            if len(display_name) > 16:
                display_name = display_name[:15] + '...'

            label_center_x = cell_x + CELL_WIDTH / 2
            svg_parts.append(
                f'<text x="{label_center_x:.2f}" y="{label_y}" '
                f'font-family="{FONT}" font-size="8" '
                f'fill="{LABEL_COLOR}" '
                f'text-anchor="middle">'
                f'{xml_escape(display_name)}</text>'
            )

            icons_embedded += 1

    # Close SVG
    svg_parts.append('</svg>')

    # -------------------------------------------------------------------
    # Write output
    # -------------------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_svg = '\n'.join(svg_parts)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(output_svg)

    file_size = os.path.getsize(OUTPUT_PATH)

    # -------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------
    print(f"Grid SVG generated: {OUTPUT_PATH}")
    print(f"  File size:       {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    print(f"  Icons embedded:  {icons_embedded}")
    if icons_failed:
        print(f"  Icons failed:    {icons_failed}")
    print(f"  Families:        {len(family_layouts)}")
    print(f"  Layout:          {TOTAL_WIDTH} x {total_height} px")
    print(f"  Grid columns:    {COLS}")
    print(f"  Cell size:       {CELL_WIDTH} x {CELL_HEIGHT} px")
    print(f"  Icon size:       {ICON_SIZE} x {ICON_SIZE} px (max)")


if __name__ == '__main__':
    main()
