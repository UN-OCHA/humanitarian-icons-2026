#!/usr/bin/env python3
"""
fix_metadata.py — Rebuild metadata.json with all corrections.

1. Family corrections: "Others" → "Other sectors"; assign families for API, Live-geoservices, P-code, Resettlement
2. Display name corrections: sentence case with acronym exceptions
3. Key corrections: match actual SVG filenames
4. Font codepoints: reassign sequentially U+E001..U+E185 in alphabetical key order
5. Wordmark data: preserve from old metadata
6. Remove "Infant feeding bottle" if present
"""

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SVG_DIR = REPO / "svg"
METADATA_FILE = REPO / "metadata.json"

# ─── Acronyms / tokens that must stay uppercase ───
UPPERCASE_TOKENS = {
    "UN", "NGO", "IDP", "COVID-19", "AI", "API", "PDF", "CSV",
    "XLSX", "DOCX", "ZIP", "UX", "UI", "E-mail", "P-code", "CCCM",
}

# For matching inside hyphenated words or standalone words
UPPERCASE_WORDS = {
    "UN", "NGO", "IDP", "AI", "API", "PDF", "CSV",
    "XLSX", "DOCX", "ZIP", "UX", "UI",
}

# ─── Old key → New key mapping (the 13 renames) ───
KEY_RENAMES = {
    "Camp-Coordination-and-Camp-Management": "Camp-coordination-and-camp-management",
    "Coordinated-assessement": "Coordinated-assessment",
    "Damaged-Affected": "Damaged-affected",
    "Early-Recovery": "Early-recovery",
    "Emergency-Telecommunications": "Emergency-telecommunications",
    "Exit-Cancel": "Exit-cancel",
    "Food-Security": "Food-security",
    "Indigenous people": "Indigenous-people",
    "Logistics_and_Telecommunications": "Logistics-and-telecommunications",
    "Sexual-and-reproductive health": "Sexual-and-reproductive-health",
    "Shelter-Land-and-Site-Coordination": "Shelter-land-and-site-coordination",
    "Warning-Error": "Warning-error",
    "Water-Sanitation-and-Hygiene": "Water-sanitation-and-hygiene",
}

# ─── Family reassignments ───
FAMILY_OVERRIDES = {
    "API": "Product type",
    "Live-geoservices": "Product type",
    "P-code": "Product type",
    "Resettlement": "People",
}

# ─── Explicit display-name overrides (new key → display name) ───
DISPLAY_NAME_OVERRIDES = {
    "Camp-coordination-and-camp-management": "Camp coordination and camp management",
    "Physical-distancing": "Physical distancing",
    "Multi-cluster-sector": "Multi-cluster sector",
    "Shelter-land-and-site-coordination": "Shelter, land and site coordination",
    "E-mail": "E-mail",
    "P-code": "P-code",
    "COVID-19": "COVID-19",
}


def to_sentence_case(name: str) -> str:
    """Convert a display name to sentence case, preserving acronyms."""
    # Handle special tokens that contain hyphens first
    # We process word by word, but need to handle "E-mail", "P-code", "COVID-19" as units.

    # Strategy: split on spaces, then for each token check if it's an acronym
    words = name.split()
    result = []

    for i, word in enumerate(words):
        # Check if the entire word (including hyphens) is a known uppercase token
        if word.upper() in {"COVID-19"}:
            result.append("COVID-19")
            continue
        if word in UPPERCASE_WORDS or word.upper() in UPPERCASE_WORDS:
            # Check if it's actually a recognized acronym
            if word.upper() in UPPERCASE_WORDS:
                result.append(word.upper())
                continue

        # Check for "(CCCM)" suffix — we remove it
        if word == "(CCCM)" or word == "CCCM":
            continue

        # For the first word: capitalize first letter, rest lowercase
        # For subsequent words: all lowercase
        # But respect acronyms within hyphenated words
        if "-" in word:
            # Handle hyphenated words like "E-mail", "P-code"
            parts = word.split("-")
            new_parts = []
            for j, part in enumerate(parts):
                if part.upper() in UPPERCASE_WORDS:
                    new_parts.append(part.upper())
                elif i == 0 and j == 0:
                    new_parts.append(part.capitalize())
                else:
                    new_parts.append(part.lower())
            result.append("-".join(new_parts))
        else:
            if i == 0:
                result.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
            else:
                result.append(word.lower())

    return " ".join(result)


def key_to_display_name(key: str) -> str:
    """Convert a key like 'Abduction-kidnapping' to display name 'Abduction kidnapping'."""
    # Check overrides first
    if key in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[key]

    # Replace hyphens with spaces, but preserve hyphens in known tokens
    # Strategy: replace hyphens with spaces, then apply sentence case,
    # then fix known hyphenated tokens

    # Build a raw name from the key
    raw = key.replace("-", " ")

    # Apply sentence case
    name = to_sentence_case(raw)

    # Restore hyphens in known tokens
    # "E mail" → "E-mail", "P code" → "P-code", "COVID 19" → "COVID-19"
    name = name.replace("E mail", "E-mail")
    name = name.replace("e mail", "E-mail")  # just in case
    name = name.replace("P code", "P-code")
    name = name.replace("p code", "P-code")
    name = name.replace("COVID 19", "COVID-19")

    return name


def main():
    # ─── 1. Read current metadata ───
    with open(METADATA_FILE) as f:
        old_data = json.load(f)

    old_icons = old_data["icons"]
    changes_log = []

    # ─── 2. Scan SVG folder for actual filenames ───
    svg_files = sorted(f for f in os.listdir(SVG_DIR) if f.endswith(".svg"))
    new_keys = [f[:-4] for f in svg_files]  # strip .svg

    print(f"SVG files found: {len(new_keys)}")
    print(f"Old metadata entries: {len(old_icons)}")

    # ─── 3. Build reverse lookup: new_key → old_key ───
    reverse_renames = {v: k for k, v in KEY_RENAMES.items()}

    # ─── 4. Build new icons dict ───
    new_icons = {}
    missing_from_old = []

    for new_key in new_keys:
        # Find the corresponding old entry
        old_key = reverse_renames.get(new_key, new_key)

        if old_key in old_icons:
            old_entry = old_icons[old_key]
        else:
            missing_from_old.append(new_key)
            # Shouldn't happen, but create a default
            old_entry = {
                "name": new_key.replace("-", " "),
                "family": "Unassigned",
                "wordmark": False,
                "wordmark_valign": 0,
                "date_added": "2026-02-13",
            }

        # ─── Generate display name ───
        display_name = key_to_display_name(new_key)

        # ─── Determine family ───
        family = old_entry["family"]

        # Family override
        if new_key in FAMILY_OVERRIDES:
            new_family = FAMILY_OVERRIDES[new_key]
            if family != new_family:
                changes_log.append(f"FAMILY: {new_key}: '{family}' → '{new_family}'")
                family = new_family

        # Rename "Others" → "Other sectors"
        if family == "Others":
            changes_log.append(f"FAMILY RENAME: {new_key}: 'Others' → 'Other sectors'")
            family = "Other sectors"

        # Fix "Unassigned" if we have a family override
        if family == "Unassigned" and new_key in FAMILY_OVERRIDES:
            family = FAMILY_OVERRIDES[new_key]

        # ─── Log key rename ───
        if old_key != new_key:
            changes_log.append(f"KEY RENAME: '{old_key}' → '{new_key}'")

        # ─── Log display name change ───
        old_name = old_entry["name"]
        if old_name != display_name:
            changes_log.append(f"DISPLAY NAME: '{old_name}' → '{display_name}' (key: {new_key})")

        new_icons[new_key] = {
            "name": display_name,
            "family": family,
            "wordmark": old_entry.get("wordmark", False),
            "wordmark_valign": old_entry.get("wordmark_valign", 0),
            "font_codepoint": "",  # will be reassigned
            "date_added": old_entry.get("date_added", "2026-02-13"),
        }

    # ─── 5. Check for "Infant feeding bottle" ───
    for key in list(new_icons.keys()):
        if "infant" in key.lower() and "feeding" in key.lower():
            changes_log.append(f"REMOVED: '{key}' (Infant feeding bottle artifact)")
            del new_icons[key]

    # Also check old metadata
    for key in old_icons:
        if "infant" in key.lower() and "feeding" in key.lower() and "bottle" in key.lower():
            changes_log.append(f"CONFIRMED REMOVED: '{key}' was in old metadata")

    # ─── 6. Sort by key alphabetically and assign codepoints ───
    sorted_keys = sorted(new_icons.keys(), key=str.casefold)
    codepoint = 0xE001
    for key in sorted_keys:
        cp_str = f"U+E{codepoint - 0xE000:03X}"
        # Format: U+E001 through U+E185
        cp_hex = f"U+{codepoint:04X}"
        new_icons[key]["font_codepoint"] = cp_hex
        codepoint += 1

    next_codepoint = f"U+{codepoint:04X}"

    # ─── 7. Build ordered icons dict (sorted by key) ───
    ordered_icons = {}
    for key in sorted_keys:
        ordered_icons[key] = new_icons[key]

    # ─── 8. Build families list ───
    # Collect all unique families from icons, maintaining desired order
    families_set = set()
    for entry in ordered_icons.values():
        families_set.add(entry["family"])

    # Use a preferred ordering, adding any extras at the end
    preferred_family_order = [
        "Clusters",
        "Other sectors",
        "Disasters, hazards and crises",
        "Socioeconomic and development",
        "People",
        "Activities Strategy",
        "Product type",
        "Food and non-food items",
        "Water sanitation and hygiene",
        "Camp",
        "Security and incident",
        "Physical barriers",
        "Damage",
        "General infrastructure",
        "Logistics",
        "Telecommunications and technology",
        "UX UI",
        "Health",
        "Lockdown",
    ]

    families = []
    for fam in preferred_family_order:
        if fam in families_set:
            families.append(fam)
            families_set.discard(fam)
    # Add any remaining
    for fam in sorted(families_set):
        families.append(fam)

    # ─── 9. Remove "Unassigned" from families if no icons use it ───
    used_families = {e["family"] for e in ordered_icons.values()}
    families = [f for f in families if f in used_families]

    # ─── 10. Build final metadata ───
    metadata = {
        "meta": {
            "version": "2.0",
            "last_updated": "2026-02-13",
            "next_font_codepoint": next_codepoint,
        },
        "families": families,
        "icons": ordered_icons,
    }

    # ─── 11. Write output ───
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # ─── 12. Print summary ───
    print(f"\n{'='*70}")
    print(f"METADATA REBUILD SUMMARY")
    print(f"{'='*70}")
    print(f"Total icons: {len(ordered_icons)}")
    print(f"Total families: {len(families)}")
    print(f"Families: {families}")
    print(f"Codepoint range: U+E001 – {f'U+{codepoint-1:04X}'}")
    print(f"Next codepoint: {next_codepoint}")
    print(f"Wordmark icons: {sum(1 for v in ordered_icons.values() if v['wordmark'])}")

    # Count changes by type
    key_renames = [c for c in changes_log if c.startswith("KEY RENAME")]
    family_changes = [c for c in changes_log if c.startswith("FAMILY")]
    name_changes = [c for c in changes_log if c.startswith("DISPLAY NAME")]
    removals = [c for c in changes_log if c.startswith("REMOVED") or c.startswith("CONFIRMED")]

    print(f"\n--- KEY RENAMES ({len(key_renames)}) ---")
    for c in sorted(key_renames):
        print(f"  {c}")

    print(f"\n--- FAMILY CHANGES ({len(family_changes)}) ---")
    for c in sorted(family_changes):
        print(f"  {c}")

    print(f"\n--- DISPLAY NAME CHANGES ({len(name_changes)}) ---")
    for c in sorted(name_changes):
        print(f"  {c}")

    if removals:
        print(f"\n--- REMOVALS ({len(removals)}) ---")
        for c in removals:
            print(f"  {c}")

    if missing_from_old:
        print(f"\n--- MISSING FROM OLD METADATA ({len(missing_from_old)}) ---")
        for k in missing_from_old:
            print(f"  {k}")

    # Verify wordmark icons
    print(f"\n--- WORDMARK ICONS (43 expected) ---")
    wm = {k: v for k, v in ordered_icons.items() if v["wordmark"]}
    for k, v in sorted(wm.items()):
        print(f"  {k}: valign={v['wordmark_valign']}")
    print(f"  Total: {len(wm)}")

    # Verify CCCM wordmark_valign
    cccm_key = "Camp-coordination-and-camp-management"
    if cccm_key in ordered_icons:
        print(f"\n  CCCM entry: wordmark={ordered_icons[cccm_key]['wordmark']}, valign={ordered_icons[cccm_key]['wordmark_valign']}")

    print(f"\n{'='*70}")
    print("Done. metadata.json has been written.")


if __name__ == "__main__":
    main()
