#!/usr/bin/env python3
"""
Generate data files for the OCHA word mark generator.

Reads metadata.json and produces:
  1. word-mark-generator/curated-icons.json  — consumed by the word mark HTML app
  2. output/Humanitarian_icons.csv           — shareable CSV of all icons

No external dependencies — uses only the Python standard library.

Usage:
    python scripts/generate-wordmark.py
"""

import csv
import io
import json
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = REPO_ROOT / "metadata.json"
CURATED_JSON_PATH = REPO_ROOT / "word-mark-generator" / "curated-icons.json"
CSV_PATH = REPO_ROOT / "output" / "Humanitarian_icons.csv"

# CDN base URL — note: repo is humanitarian-icons-2026, SVG folder is svg/
CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/UN-OCHA/humanitarian-icons-2026@main/svg/"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_metadata() -> dict:
    """Load and return the parsed metadata.json."""
    with open(METADATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def icons_by_family(metadata: dict) -> dict[str, list[tuple[str, dict]]]:
    """
    Group icons by family, preserving the (key, icon_data) pairs.

    Returns a dict mapping family name -> list of (key, icon_data), where
    each list is sorted alphabetically by display name.
    """
    families_order = metadata["families"]
    icons = metadata["icons"]

    grouped: dict[str, list[tuple[str, dict]]] = {f: [] for f in families_order}

    for key, icon in icons.items():
        family = icon["family"]
        if family in grouped:
            grouped[family].append((key, icon))
        else:
            grouped.setdefault(family, []).append((key, icon))

    # Sort each family's icons alphabetically by display name
    for family in grouped:
        grouped[family].sort(key=lambda pair: pair[1]["name"].lower())

    return grouped


# ---------------------------------------------------------------------------
# Output 1: curated-icons.json
# ---------------------------------------------------------------------------

def build_curated_json(metadata: dict) -> dict:
    """
    Build the curated-icons.json structure:

    {
      "categories": [
        { "name": "Clusters", "icons": ["Camp coordination ...", ...] },
        ...
      ],
      "icons": [
        {
          "name": "Camp coordination and camp management",
          "url": "https://cdn.jsdelivr.net/.../Camp-coordination-and-camp-management.svg",
          "verticalAdjustment": -2,
          "category": "Clusters"
        },
        ...
      ]
    }

    - categories: ALL icons grouped by family (full list).
    - icons: ONLY those with wordmark == true (the curated subset).
    """
    families_order = metadata["families"]
    grouped = icons_by_family(metadata)

    # Build the categories array — every icon, grouped by family order
    categories = []
    for family in families_order:
        icon_names = [icon["name"] for _key, icon in grouped.get(family, [])]
        categories.append({
            "name": family,
            "icons": icon_names,
        })

    # Handle any families not in the canonical order (safety net)
    known = set(families_order)
    for family in grouped:
        if family not in known:
            icon_names = [icon["name"] for _key, icon in grouped[family]]
            categories.append({
                "name": family,
                "icons": icon_names,
            })

    # Build the icons array — only wordmark: true icons
    curated_icons = []
    for family in families_order:
        for key, icon in grouped.get(family, []):
            if icon.get("wordmark"):
                curated_icons.append({
                    "name": icon["name"],
                    "url": f"{CDN_BASE}{key}.svg",
                    "verticalAdjustment": icon.get("wordmark_valign", 0),
                    "category": icon["family"],
                })

    # Also pick up wordmark icons from unknown families (safety net)
    for family in grouped:
        if family not in known:
            for key, icon in grouped[family]:
                if icon.get("wordmark"):
                    curated_icons.append({
                        "name": icon["name"],
                        "url": f"{CDN_BASE}{key}.svg",
                        "verticalAdjustment": icon.get("wordmark_valign", 0),
                        "category": icon["family"],
                    })

    return {
        "categories": categories,
        "icons": curated_icons,
    }


def write_curated_json(data: dict) -> None:
    """Write curated-icons.json with 2-space indentation."""
    CURATED_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CURATED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")  # trailing newline


# ---------------------------------------------------------------------------
# Output 2: Humanitarian_icons.csv
# ---------------------------------------------------------------------------

def write_csv(metadata: dict) -> int:
    """
    Write a UTF-8 CSV (with BOM) containing all icons.

    Format:
        Family,Icon Name
        Clusters,Camp coordination and camp management
        ...

    Returns the number of data rows written.
    """
    grouped = icons_by_family(metadata)
    families_order = metadata["families"]

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    row_count = 0
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Family", "Icon Name"])

        for family in families_order:
            for _key, icon in grouped.get(family, []):
                writer.writerow([family, icon["name"]])
                row_count += 1

        # Safety net for unknown families
        known = set(families_order)
        for family in grouped:
            if family not in known:
                for _key, icon in grouped[family]:
                    writer.writerow([family, icon["name"]])
                    row_count += 1

    return row_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Reading metadata from {METADATA_PATH}")
    metadata = load_metadata()

    families = metadata["families"]
    icons = metadata["icons"]
    total_icons = len(icons)
    print(f"  Found {total_icons} icons across {len(families)} families")

    # --- curated-icons.json ---
    curated_data = build_curated_json(metadata)
    write_curated_json(curated_data)

    num_categories = len(curated_data["categories"])
    num_all_in_categories = sum(len(c["icons"]) for c in curated_data["categories"])
    num_wordmark = len(curated_data["icons"])

    print(f"  Wrote {CURATED_JSON_PATH}")
    print(f"    categories: {num_categories} families, {num_all_in_categories} total icons")
    print(f"    wordmark icons: {num_wordmark}")

    # --- CSV ---
    csv_rows = write_csv(metadata)
    print(f"  Wrote {CSV_PATH}")
    print(f"    {csv_rows} data rows (UTF-8 with BOM)")

    print("Done.")


if __name__ == "__main__":
    main()
