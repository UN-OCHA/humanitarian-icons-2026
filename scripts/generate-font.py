#!/usr/bin/env python3
"""
generate-font.py — Generate an icon font from OCHA humanitarian SVG icons.

Reads metadata.json for permanently assigned Unicode codepoints (U+E001, etc.)
and builds an SVG-in-OpenType font (.ttf + .woff2) plus an HTML reference page.

Dependencies: fonttools, brotli  (install via pip)
"""

import json
import os
import re
import sys
import time
from xml.etree import ElementTree as ET

from fontTools import ttLib
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib.tables.S_V_G_ import SVGDocument

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FONT_FAMILY = "OCHA Humanitarian Icons"
FONT_VERSION = "Version 2.0"
FONT_COPYRIGHT = "Copyright (c) United Nations OCHA"
UPM = 1000          # units per em
ASCENT = 800
DESCENT = -200

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
METADATA_PATH = os.path.join(REPO_ROOT, "metadata.json")
SVG_DIR = os.path.join(REPO_ROOT, "svg")
OUTPUT_DIR = os.path.join(REPO_ROOT, "output", "font")
TTF_PATH = os.path.join(OUTPUT_DIR, "ocha-humanitarian-icons.ttf")
WOFF2_PATH = os.path.join(OUTPUT_DIR, "ocha-humanitarian-icons.woff2")
HTML_PATH = os.path.join(OUTPUT_DIR, "index.html")


# ---------------------------------------------------------------------------
# SVG cleaning helpers
# ---------------------------------------------------------------------------
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

STRIP_ELEMENTS = {
    f"{{{SVG_NS}}}defs",
    f"{{{SVG_NS}}}style",
    f"{{{SVG_NS}}}title",
}

STRIP_ATTRS = {"class", "id", "data-name"}


def clean_svg_for_font(svg_text: str, glyph_id: int) -> str | None:
    """
    Parse an SVG file, strip styles/defs/fills, and return an <svg> document
    suitable for embedding in an SVG-in-OpenType font table.

    The glyph SVG must:
      - Use id="glyph{glyph_id}" on the root <svg>
      - Be scaled to fit the UPM grid (1000 units tall)
      - Have no fill attributes (inherits currentColor)
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        print(f"  WARNING: SVG parse error: {exc}")
        return None

    # ---- Extract viewBox dimensions ----
    vb = root.get("viewBox", "")
    parts = vb.split()
    if len(parts) != 4:
        print(f"  WARNING: bad viewBox '{vb}'")
        return None
    vb_x, vb_y, vb_w, vb_h = (float(p) for p in parts)

    if vb_w <= 0 or vb_h <= 0:
        return None

    # ---- Compute scaling ----
    # We want the SVG to fit in (UPM x UPM), preserving aspect ratio.
    # The font's em-square is UPM tall (ascent + |descent| = 1000).
    # We scale so the taller dimension fits in UPM.
    scale = UPM / max(vb_w, vb_h)
    new_w = vb_w * scale
    new_h = vb_h * scale

    # Center horizontally in UPM if narrower
    offset_x = (UPM - new_w) / 2.0
    # Center vertically in UPM
    offset_y = (UPM - new_h) / 2.0

    # ---- Strip unwanted elements recursively ----
    def strip_recursive(elem):
        to_remove = []
        for child in elem:
            if child.tag in STRIP_ELEMENTS:
                to_remove.append(child)
            else:
                strip_recursive(child)
        for child in to_remove:
            elem.remove(child)

    strip_recursive(root)

    # ---- Strip unwanted attributes and fills ----
    def clean_attrs(elem):
        for attr in list(elem.attrib):
            local = attr.split("}")[-1] if "}" in attr else attr
            if local in STRIP_ATTRS:
                del elem.attrib[attr]
            elif local == "fill":
                del elem.attrib[attr]
            elif local == "style":
                # Remove fill from inline style
                style = elem.get("style", "")
                style = re.sub(r"fill\s*:\s*[^;]+;?", "", style).strip()
                if style:
                    elem.set("style", style)
                else:
                    del elem.attrib["style"]
        for child in elem:
            clean_attrs(child)

    clean_attrs(root)

    # ---- Build the glyph SVG document ----
    # The SVG table requires each document to have id="glyphNN"
    # where NN is the glyph index.
    # We wrap the icon content in a transform group to scale/position it.
    inner_parts = []
    for child in root:
        inner_parts.append(ET.tostring(child, encoding="unicode"))
    inner_svg = "".join(inner_parts)

    # Build new SVG document string
    # The SVG-in-OpenType spec: the SVG doc viewBox maps to the em-square.
    # We set viewBox to 0 0 UPM UPM and transform the content.
    svg_doc = (
        f'<svg xmlns="http://www.w3.org/2000/svg" id="glyph{glyph_id}">'
        f'<g transform="translate({offset_x:.4f},{offset_y:.4f}) scale({scale:.6f})">'
        f"{inner_svg}"
        f"</g></svg>"
    )
    return svg_doc


# ---------------------------------------------------------------------------
# Font building
# ---------------------------------------------------------------------------

def parse_codepoint(cp_str: str) -> int:
    """Parse 'U+E001' into integer 0xE001."""
    return int(cp_str.replace("U+", "").replace("u+", ""), 16)


def build_font(icons_data: list[dict]) -> ttLib.TTFont:
    """
    Build a TTF with an SVG table.

    icons_data: list of dicts with keys:
        slug, name, codepoint (int), svg_doc (str), glyph_name (str)
    """
    # Sort by codepoint for consistency
    icons_data.sort(key=lambda d: d["codepoint"])

    glyph_order = [".notdef"]
    glyph_names = [".notdef"]
    cmap = {}
    svg_docs = []
    advance_widths = {".notdef": UPM}
    glyph_name_set = set()

    for i, icon in enumerate(icons_data):
        gname = icon["glyph_name"]
        # Ensure unique glyph names
        if gname in glyph_name_set:
            gname = f"{gname}.{i}"
        glyph_name_set.add(gname)
        icon["glyph_name"] = gname

        glyph_order.append(gname)
        glyph_names.append(gname)
        cmap[icon["codepoint"]] = gname
        advance_widths[gname] = UPM

        glyph_index = i + 1  # .notdef is 0
        svg_docs.append(
            SVGDocument(
                icon["svg_doc"],
                startGlyphID=glyph_index,
                endGlyphID=glyph_index,
            )
        )

    num_glyphs = len(glyph_order)

    # ---- Build with FontBuilder ----
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)

    # Character map
    fb.setupCharacterMap(cmap)

    # Draw empty glyph outlines (the actual rendering comes from SVG table).
    # We need to use the pen API to create proper empty Glyph objects.
    fb.setupGlyf({})
    glyf_table = fb.font["glyf"]
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    for gn in glyph_order:
        glyf_table[gn] = Glyph()

    # Horizontal metrics — all glyphs get full UPM advance
    metrics = {}
    for gn in glyph_order:
        metrics[gn] = (UPM, 0)  # (advance width, LSB)
    fb.setupHorizontalMetrics(metrics)

    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    # Mac epoch offset: seconds from 1904-01-01 to 1970-01-01
    MAC_EPOCH_OFFSET = 2082844800
    now = int(time.time()) + MAC_EPOCH_OFFSET
    fb.setupHead(unitsPerEm=UPM, created=now, modified=now)

    fb.setupOS2(
        sTypoAscender=ASCENT,
        sTypoDescender=DESCENT,
        sTypoLineGap=0,
        usWinAscent=ASCENT,
        usWinDescent=abs(DESCENT),
        sxHeight=500,
        sCapHeight=700,
    )
    fb.setupPost()

    fb.setupNameTable({
        "familyName": FONT_FAMILY,
        "styleName": "Regular",
        "psName": "OCHAHumanitarianIcons-Regular",
        "uniqueFontIdentifier": f"{FONT_COPYRIGHT};{FONT_FAMILY}-Regular",
        "version": FONT_VERSION,
        "copyright": FONT_COPYRIGHT,
    })

    font = fb.font

    # ---- Add SVG table ----
    svg_table = ttLib.newTable("SVG ")
    svg_table.docList = svg_docs
    font["SVG "] = svg_table

    return font


# ---------------------------------------------------------------------------
# HTML reference page
# ---------------------------------------------------------------------------

def generate_html(icons_data: list[dict], families: list[str]) -> str:
    """Generate an HTML reference page grouped by family."""

    # Group icons by family
    by_family: dict[str, list[dict]] = {f: [] for f in families}
    for icon in icons_data:
        fam = icon["family"]
        if fam in by_family:
            by_family[fam].append(icon)
        else:
            by_family[fam] = [icon]

    # Sort each family alphabetically by name
    for fam in by_family:
        by_family[fam].sort(key=lambda d: d["name"].lower())

    # Build icon grid HTML
    grid_sections = []
    for fam in families:
        fam_icons = by_family.get(fam, [])
        if not fam_icons:
            continue
        cards = []
        for icon in fam_icons:
            cp_hex = f"U+{icon['codepoint']:04X}"
            char = chr(icon["codepoint"])
            cards.append(
                f'      <div class="icon-card" data-name="{icon["name"].lower()}" data-family="{fam.lower()}">\n'
                f'        <div class="icon-char" title="Click to copy">{char}</div>\n'
                f'        <div class="icon-name">{icon["name"]}</div>\n'
                f'        <div class="icon-code">{cp_hex}</div>\n'
                f"      </div>"
            )
        section = (
            f'    <div class="family-section">\n'
            f'      <h2 class="family-header">{fam}</h2>\n'
            f'      <div class="icon-grid">\n'
            + "\n".join(cards) + "\n"
            f"      </div>\n"
            f"    </div>"
        )
        grid_sections.append(section)

    total = len(icons_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OCHA Humanitarian Icons — Font Reference</title>
<style>
@font-face {{
  font-family: "{FONT_FAMILY}";
  src: url("ocha-humanitarian-icons.woff2") format("woff2"),
       url("ocha-humanitarian-icons.ttf") format("truetype");
  font-weight: normal;
  font-style: normal;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  background: #f5f6fa;
  color: #2d3436;
  line-height: 1.5;
  padding: 2rem;
}}

.header {{
  max-width: 1200px;
  margin: 0 auto 2rem;
  text-align: center;
}}

.header h1 {{
  font-size: 1.8rem;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 0.25rem;
}}

.header .subtitle {{
  font-size: 0.95rem;
  color: #636e72;
  margin-bottom: 1.5rem;
}}

.search-box {{
  max-width: 480px;
  margin: 0 auto 2rem;
  position: relative;
}}

.search-box input {{
  width: 100%;
  padding: 0.75rem 1rem 0.75rem 2.75rem;
  font-size: 1rem;
  border: 2px solid #dfe6e9;
  border-radius: 8px;
  background: #fff;
  outline: none;
  transition: border-color 0.2s;
}}

.search-box input:focus {{
  border-color: #009edb;
}}

.search-box::before {{
  content: "\\2315";
  position: absolute;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 1.2rem;
  color: #b2bec3;
  pointer-events: none;
}}

.container {{
  max-width: 1200px;
  margin: 0 auto;
}}

.family-section {{
  margin-bottom: 2.5rem;
}}

.family-header {{
  font-size: 1.15rem;
  font-weight: 600;
  color: #fff;
  background: #009edb;
  padding: 0.6rem 1.2rem;
  border-radius: 6px;
  margin-bottom: 1rem;
}}

.icon-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 0.75rem;
}}

.icon-card {{
  background: #fff;
  border-radius: 8px;
  padding: 1rem 0.5rem;
  text-align: center;
  border: 1px solid #eee;
  transition: box-shadow 0.15s, transform 0.15s;
  cursor: default;
}}

.icon-card:hover {{
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  transform: translateY(-2px);
}}

.icon-card.hidden {{
  display: none;
}}

.icon-char {{
  font-family: "{FONT_FAMILY}";
  font-size: 2.5rem;
  line-height: 1;
  color: #009edb;
  margin-bottom: 0.5rem;
  cursor: pointer;
  user-select: all;
  -webkit-user-select: all;
}}

.icon-name {{
  font-size: 0.75rem;
  font-weight: 500;
  color: #2d3436;
  margin-bottom: 0.2rem;
  word-break: break-word;
}}

.icon-code {{
  font-size: 0.7rem;
  color: #b2bec3;
  font-family: "SF Mono", "Fira Code", "Fira Mono", monospace;
}}

.no-results {{
  display: none;
  text-align: center;
  padding: 3rem;
  color: #636e72;
  font-size: 1.1rem;
}}

.family-section.hidden {{
  display: none;
}}

footer {{
  text-align: center;
  margin-top: 3rem;
  padding: 1rem;
  color: #b2bec3;
  font-size: 0.8rem;
}}
</style>
</head>
<body>

<div class="header">
  <h1>OCHA Humanitarian Icons</h1>
  <p class="subtitle">{total} icons &middot; Font version 2.0 &middot; United Nations OCHA</p>
</div>

<div class="search-box">
  <input type="text" id="searchInput" placeholder="Filter icons by name..." autocomplete="off" />
</div>

<div class="container" id="iconContainer">
{"".join(grid_sections)}
</div>

<div class="no-results" id="noResults">No icons match your search.</div>

<footer>
  OCHA Humanitarian Icons &mdash; {FONT_COPYRIGHT}
</footer>

<script>
(function() {{
  const input = document.getElementById('searchInput');
  const container = document.getElementById('iconContainer');
  const noResults = document.getElementById('noResults');
  const cards = container.querySelectorAll('.icon-card');
  const sections = container.querySelectorAll('.family-section');

  input.addEventListener('input', function() {{
    const q = this.value.trim().toLowerCase();
    let visibleCount = 0;

    cards.forEach(card => {{
      const name = card.getAttribute('data-name') || '';
      const show = !q || name.includes(q);
      card.classList.toggle('hidden', !show);
      if (show) visibleCount++;
    }});

    // Hide empty family sections
    sections.forEach(sec => {{
      const visibleCards = sec.querySelectorAll('.icon-card:not(.hidden)');
      sec.classList.toggle('hidden', visibleCards.length === 0);
    }});

    noResults.style.display = visibleCount === 0 ? 'block' : 'none';
  }});
}})();
</script>

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"OCHA Humanitarian Icons — Font Generator")
    print(f"{'=' * 50}")

    # ---- Load metadata ----
    if not os.path.isfile(METADATA_PATH):
        print(f"ERROR: metadata.json not found at {METADATA_PATH}")
        sys.exit(1)

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    families = metadata.get("families", [])
    icons_meta = metadata.get("icons", {})
    print(f"Loaded {len(icons_meta)} icons from metadata.json")

    # ---- Validate codepoints ----
    missing_codepoint = []
    for slug, info in icons_meta.items():
        cp = info.get("font_codepoint", "")
        if not cp:
            missing_codepoint.append(slug)

    if missing_codepoint:
        print(f"\nERROR: {len(missing_codepoint)} icon(s) missing font_codepoint:")
        for slug in sorted(missing_codepoint):
            print(f"  - {slug}")
        sys.exit(1)

    # ---- Process SVGs ----
    icons_data = []
    failed = []
    codepoint_map = {}  # check for duplicate codepoints

    for slug, info in sorted(icons_meta.items()):
        cp_str = info["font_codepoint"]
        cp_int = parse_codepoint(cp_str)
        name = info.get("name", slug)
        family = info.get("family", "Uncategorized")

        # Check duplicate codepoint
        if cp_int in codepoint_map:
            print(f"  WARNING: duplicate codepoint {cp_str} for '{slug}' (already used by '{codepoint_map[cp_int]}')")
        codepoint_map[cp_int] = slug

        svg_path = os.path.join(SVG_DIR, f"{slug}.svg")
        if not os.path.isfile(svg_path):
            print(f"  SKIP: SVG not found for '{slug}' at {svg_path}")
            failed.append((slug, "SVG file not found"))
            continue

        with open(svg_path, "r", encoding="utf-8") as f:
            svg_text = f.read()

        # glyph index: will be determined after sorting
        # Use a placeholder; we'll fix after sorting
        svg_doc = clean_svg_for_font(svg_text, glyph_id=0)
        if svg_doc is None:
            print(f"  SKIP: SVG processing failed for '{slug}'")
            failed.append((slug, "SVG processing error"))
            continue

        # Make a safe glyph name (PostScript-compatible)
        glyph_name = f"uni{cp_int:04X}"

        icons_data.append({
            "slug": slug,
            "name": name,
            "family": family,
            "codepoint": cp_int,
            "glyph_name": glyph_name,
            "svg_doc": svg_doc,
        })

    # Sort by codepoint and fix glyph IDs in SVG docs
    icons_data.sort(key=lambda d: d["codepoint"])
    for i, icon in enumerate(icons_data):
        glyph_index = i + 1  # .notdef is glyph 0
        # Update the SVG doc id to match glyph index
        icon["svg_doc"] = icon["svg_doc"].replace(
            'id="glyph0"', f'id="glyph{glyph_index}"'
        )

    print(f"\nProcessed {len(icons_data)} icons successfully")
    if failed:
        print(f"Failed: {len(failed)} icons:")
        for slug, reason in failed:
            print(f"  - {slug}: {reason}")

    if not icons_data:
        print("ERROR: No icons to process!")
        sys.exit(1)

    # ---- Build font ----
    print(f"\nBuilding font...")
    font = build_font(icons_data)

    # ---- Save outputs ----
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save TTF
    font.save(TTF_PATH)
    ttf_size = os.path.getsize(TTF_PATH)
    print(f"  TTF: {TTF_PATH}")
    print(f"       {ttf_size:,} bytes ({ttf_size / 1024:.1f} KB)")

    # Save WOFF2
    font.flavor = "woff2"
    font.save(WOFF2_PATH)
    woff2_size = os.path.getsize(WOFF2_PATH)
    print(f"  WOFF2: {WOFF2_PATH}")
    print(f"         {woff2_size:,} bytes ({woff2_size / 1024:.1f} KB)")

    # ---- Generate HTML ----
    print(f"\nGenerating HTML reference page...")
    html = generate_html(icons_data, families)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    html_size = os.path.getsize(HTML_PATH)
    print(f"  HTML: {HTML_PATH}")
    print(f"        {html_size:,} bytes ({html_size / 1024:.1f} KB)")

    # ---- Summary ----
    print(f"\n{'=' * 50}")
    print(f"DONE")
    print(f"  Total glyphs: {len(icons_data)} (+ .notdef)")
    print(f"  Codepoint range: U+{icons_data[0]['codepoint']:04X} - U+{icons_data[-1]['codepoint']:04X}")
    print(f"  TTF size:   {ttf_size / 1024:.1f} KB")
    print(f"  WOFF2 size: {woff2_size / 1024:.1f} KB")
    if failed:
        print(f"  Failed icons: {len(failed)}")
    print()

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
