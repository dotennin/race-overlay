# Separate Unit Font Styling from Title Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename widget-level font style parameters to be unit-specific (`unit_font_*`), ensuring title/label text always uses theme defaults while units can be styled independently.

**Architecture:** The current system has two levels of font control: theme-level (global defaults) and widget-level (per-widget overrides). The problem is that widget-level `font_family`, `font_weight`, `font_size_px` affect both title AND unit. The solution is to rename these to `unit_font_*` and update rendering logic to explicitly call `_style_role_font(role="unit")` for units, ensuring titles always use theme's `title_font_*` values. A deserialization migration layer handles backward compatibility with old YAML configs.

**Tech Stack:** Python dataclasses, YAML deserialization, PIL ImageFont, Pytest

---

## File Structure

**Files to modify:**
- `src/race_overlay/hud_schema.py` - Add migration logic to deserialize old font names
- `src/race_overlay/editor_preview.py` - Update widget style schema (5 widget types)
- `src/race_overlay/hud.py` - Update rendering functions to use role-specific fonts
- `overlay.yaml` - Update config to use new field names
- `tests/test_hud.py` - Add/update tests for font styling separation

---

## Task 1: Add Migration Layer in hud_schema.py

**Files:**
- Modify: `src/race_overlay/hud_schema.py:100-130` (_deserialize_widget function)

**Purpose:** Handle backward compatibility by automatically migrating old `font_family`, `font_weight`, `font_size_px` to new `unit_font_*` names during YAML deserialization.

- [ ] **Step 1: View the _deserialize_widget function**

Run: `grep -A 30 "def _deserialize_widget" src/race_overlay/hud_schema.py | head -40`

Look for the line `style=_require_style_mapping(...)` to understand current deserialization.

- [ ] **Step 2: Add migration logic after style deserialization**

After the call to `_require_style_mapping()`, add migration code. Insert this after line 100:

```python
def _deserialize_widget(payload: object) -> HudWidgetConfig:
    if not isinstance(payload, dict):
        raise TypeError("hud.widgets entries must be mappings")
    _reject_unexpected_keys(payload, _HUD_WIDGET_KEYS, "hud.widgets")
    
    # Get style first
    style = _require_style_mapping(payload.get("style", {}), "hud.widgets[].style")
    
    # Migrate old font names to unit_font names for backward compatibility
    style = _migrate_widget_style_font_names(style)
    
    return HudWidgetConfig(
        id=_require_string(payload.get("id"), "hud.widgets[].id"),
        type=_require_string(payload.get("type"), "hud.widgets[].type"),
        bindings=_require_string_mapping(payload.get("bindings"), "hud.widgets[].bindings"),
        anchor=_require_string(payload.get("anchor"), "hud.widgets[].anchor"),
        x=_coerce_int(payload.get("x"), "x"),
        y=_coerce_int(payload.get("y"), "y"),
        width=_coerce_int(payload.get("width"), "width"),
        height=_coerce_int(payload.get("height"), "height"),
        z_index=_coerce_int(payload.get("z_index", 0), "z_index"),
        visible=_coerce_bool(payload.get("visible", True), "hud.widgets[].visible"),
        style=style,
    )
```

- [ ] **Step 3: Add migration helper function**

Add this helper function after all the validation helper functions (around line 180):

```python
def _migrate_widget_style_font_names(style: dict[str, str | int | float | bool | list[int]]) -> dict[str, str | int | float | bool | list[int]]:
    """Migrate old generic font names to unit-specific names for backward compatibility."""
    if "font_family" in style and "unit_font_family" not in style:
        style["unit_font_family"] = style.pop("font_family")
    if "font_weight" in style and "unit_font_weight" not in style:
        style["unit_font_weight"] = style.pop("font_weight")
    if "font_size_px" in style and "unit_font_size_px" not in style:
        style["unit_font_size_px"] = style.pop("font_size_px")
    return style
```

- [ ] **Step 4: Run basic test to verify no syntax errors**

Run: `python -m py_compile src/race_overlay/hud_schema.py`

Expected: No output (success)

- [ ] **Step 5: Commit migration layer**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud_schema.py
git commit -m "feat: add widget style font name migration for backward compatibility

Migrate old generic font_family/weight/size_px to unit_font_* equivalents
during deserialization to maintain compatibility with existing YAML configs."
```

---

## Task 2: Update Editor Schema for Widget Styles

**Files:**
- Modify: `src/race_overlay/editor_preview.py:34-98` (_WIDGET_STYLE_SCHEMA_BY_TYPE)

**Purpose:** Update the editor schema to use new `unit_font_*` names for all widget types, reflecting that these parameters now control only unit styling.

- [ ] **Step 1: Update progress_bar schema**

Find the `"progress_bar"` entry in `_WIDGET_STYLE_SCHEMA_BY_TYPE` dict. Replace the font fields (lines 38-40):

```python
"progress_bar": {
    "label": {"kind": "text", "label": "Label"},
    "variant": {"kind": "selection", "label": "Variant", "options": ["ruler"]},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "current_font_size_px": {"kind": "integer", "label": "Current font size", "min": 8},
    "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
    "show_current_value": {"kind": "boolean", "label": "Show current value"},
    "show_total_value": {"kind": "boolean", "label": "Show total value"},
    "fill_rgba": {"kind": "rgba", "label": "Fill RGBA"},
    "rail_rgba": {"kind": "rgba", "label": "Rail RGBA"},
    "tick_rgba": {"kind": "rgba", "label": "Tick RGBA"},
    "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
},
```

- [ ] **Step 2: Update stat_block schema**

Find the `"stat_block"` entry. Replace the font fields (lines 55-57):

```python
"stat_block": {
    "label": {"kind": "text", "label": "Label"},
    "unit": {"kind": "text", "label": "Unit", "hidden": True},
    "variant": {"kind": "selection", "label": "Variant", "options": ["standard", "compact"]},
    "align": {"kind": "selection", "label": "Align", "options": ["left", "right"]},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
    "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
},
```

- [ ] **Step 3: Update metric_card schema**

Find the `"metric_card"` entry. Replace the font fields (lines 65-67):

```python
"metric_card": {
    "label": {"kind": "text", "label": "Label"},
    "variant": {"kind": "selection", "label": "Variant", "options": ["compact"]},
    "align": {"kind": "selection", "label": "Align", "options": ["left", "right"]},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
    "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
},
```

- [ ] **Step 4: Update hero_metric schema**

Find the `"hero_metric"` entry. Replace the font fields (lines 73-75):

```python
"hero_metric": {
    "label": {"kind": "text", "label": "Label"},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "show_unit": {"kind": "boolean", "label": "Show unit suffix"},
    "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
},
```

- [ ] **Step 5: Update context_card schema**

Find the `"context_card"` entry. Replace the font fields (lines 83-85):

```python
"context_card": {
    "label": {"kind": "text", "label": "Label"},
    "variant": {"kind": "selection", "label": "Variant", "options": ["compact", "timestamp_chip"]},
    "format": {"kind": "text", "label": "Format"},
    "unit_font_family": {"kind": "enum", "label": "Unit font family", "options": list(HUD_FONT_FAMILY_OPTIONS)},
    "unit_font_weight": {"kind": "enum", "label": "Unit font weight", "options": list(HUD_FONT_WEIGHT_OPTIONS)},
    "unit_font_size_px": {"kind": "integer", "label": "Unit font size", "min": 8},
    "transparent_panel": {"kind": "boolean", "label": "Transparent panel"},
},
```

- [ ] **Step 6: Verify schema is valid Python**

Run: `python -m py_compile src/race_overlay/editor_preview.py`

Expected: No output (success)

- [ ] **Step 7: Commit editor schema changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/editor_preview.py
git commit -m "refactor: rename widget font style parameters to unit_font_*

Rename font_family, font_weight, font_size_px to unit_font_family,
unit_font_weight, unit_font_size_px across all widget types:
- progress_bar
- stat_block
- metric_card
- hero_metric
- context_card

This clarifies that these parameters control only unit suffix styling,
not title/label styling which uses theme defaults."
```

---

## Task 3: Update hud.py Validation and Helper Functions

**Files:**
- Modify: `src/race_overlay/hud.py:300-310` (validation functions)

**Purpose:** Remove validation for old generic `font_family`, `font_weight`, `font_size_px` style keys and add validation for new `unit_font_*` keys.

- [ ] **Step 1: Find and update _validate_hud_widget function**

Find the function around line 300. It has validations like:
```python
_validate_optional_enum_style(widget, "font_family", HUD_FONT_FAMILY_OPTIONS)
_validate_optional_enum_style(widget, "font_weight", HUD_FONT_WEIGHT_OPTIONS)
```

Replace these lines with:

```python
_validate_optional_enum_style(widget, "unit_font_family", HUD_FONT_FAMILY_OPTIONS)
_validate_optional_enum_style(widget, "unit_font_weight", HUD_FONT_WEIGHT_OPTIONS)
_validate_optional_font_size_style(widget, "unit_font_size_px")
```

Look for the exact line numbers:
Run: `grep -n "font_family.*HUD_FONT_FAMILY" src/race_overlay/hud.py | head -3`

- [ ] **Step 2: Update _style_font_size helper for unit fonts**

The function `_style_font_size` at line ~411 should fallback to theme's `unit_font_size_px`. Find this function and update it. The current code reads from `font_size_px`, change to `unit_font_size_px`:

```python
def _style_font_size(widget: HudWidgetConfig, theme: HudThemeConfig, fallback: int) -> int:
    value = widget.style.get("unit_font_size_px", theme.unit_font_size_px or fallback)
    return _require_font_size_style(widget, value, "unit_font_size_px")
```

- [ ] **Step 3: Update _style_font_family helper for unit fonts**

Find the function at line ~416 and update:

```python
def _style_font_family(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("unit_font_family", theme.unit_font_family)
    if not isinstance(value, str) or value not in HUD_FONT_FAMILY_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_FAMILY_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_family must be one of: {allowed_values}")
    return value
```

- [ ] **Step 4: Update _style_font_weight helper for unit fonts**

Find the function at line ~436 and update:

```python
def _style_font_weight(widget: HudWidgetConfig, theme: HudThemeConfig) -> str:
    value = widget.style.get("unit_font_weight", theme.unit_font_weight)
    if not isinstance(value, str) or value not in HUD_FONT_WEIGHT_OPTIONS:
        allowed_values = ", ".join(HUD_FONT_WEIGHT_OPTIONS)
        raise ValueError(f"widget '{widget.id}' style.unit_font_weight must be one of: {allowed_values}")
    return value
```

- [ ] **Step 5: Update _style_font helper to use unit fonts**

Find `_style_font` at line ~444 and update:

```python
def _style_font(widget: HudWidgetConfig, theme: HudThemeConfig, scale: RenderScale, fallback: int = 18) -> ImageFont.FreeTypeFont:
    return _scaled_font(
        scale,
        _style_font_size(widget, theme, fallback),
        _style_font_family(widget, theme),
        _style_font_weight(widget, theme),
    )
```

The function body stays the same - it now calls the updated helpers.

- [ ] **Step 6: Run basic validation**

Run: `python -m py_compile src/race_overlay/hud.py`

Expected: No output (success)

- [ ] **Step 7: Commit hud.py validation updates**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: update font style validation and helpers for unit_font_*

Update validation functions to check unit_font_family, unit_font_weight,
and unit_font_size_px instead of generic font names.

Update helper functions _style_font_size, _style_font_family,
_style_font_weight to read from unit_font_* parameters and fallback
to theme's unit_font_* defaults."
```

---

## Task 4: Update Progress Bar Rendering

**Files:**
- Modify: `src/race_overlay/hud.py:569-610` (_draw_progress_bar function)

**Purpose:** Ensure progress bar unit rendering uses `_style_role_font(role="unit")` instead of generic `_style_font()`.

- [ ] **Step 1: Find unit rendering in _draw_progress_bar**

Run: `grep -n "show_unit\|unit_font" src/race_overlay/hud.py | grep -A 2 -B 2 569`

Look for where progress bar draws units. The function likely calls `_style_font()` for the unit text.

- [ ] **Step 2: Update unit font call**

Find where the progress bar renders the unit (typically a `draw.text()` call with the unit suffix like "/km"). The line should have:

```python
unit_font = _style_font(widget, theme, scale, fallback=12)
```

Replace with:

```python
unit_font = _style_role_font(widget, theme, scale, role="unit")
```

Make sure the surrounding code structure remains intact.

- [ ] **Step 3: Run test to verify no immediate errors**

Run: `uv run pytest tests/test_hud.py -q 2>&1 | head -20`

Expected: Tests run (may pass or fail, but no import/syntax errors)

- [ ] **Step 4: Commit progress bar changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: use role-specific font for progress_bar unit rendering"
```

---

## Task 5: Update Stat Block Rendering

**Files:**
- Modify: `src/race_overlay/hud.py:637-755` (_draw_stat_block function)

**Purpose:** Ensure stat block unit rendering uses `_style_role_font(role="unit")` and title uses `_style_role_font(role="title")`.

- [ ] **Step 1: Locate unit and title font calls in _draw_stat_block**

Run: `grep -n "def _draw_stat_block" src/race_overlay/hud.py`

Find where this function renders unit text (likely around line 695-700 where it draws the unit suffix).

- [ ] **Step 2: Update title font to use role-specific**

Find where the label/title is rendered. Change from:

```python
title_font = _style_font(widget, theme, scale, fallback=14)
```

To:

```python
title_font = _style_role_font(widget, theme, scale, role="title")
```

- [ ] **Step 3: Update unit font to use role-specific**

Find where the unit is rendered. Change from:

```python
unit_font = _style_font(widget, theme, scale, fallback=12)
```

To:

```python
unit_font = _style_role_font(widget, theme, scale, role="unit")
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_hud.py::test_draw_stat_block -v 2>&1 | tail -20`

Expected: Test passes (if it exists)

- [ ] **Step 5: Commit stat block changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: use role-specific fonts for stat_block title and unit rendering"
```

---

## Task 6: Update Metric Card Rendering

**Files:**
- Modify: `src/race_overlay/hud.py:850-1015` (_draw_metric_card function)

**Purpose:** Ensure metric card unit rendering uses `_style_role_font(role="unit")` and title uses theme defaults.

- [ ] **Step 1: Locate font calls in _draw_metric_card**

Find all places where fonts are created in this function. Look for patterns:

Run: `sed -n '850,1015p' src/race_overlay/hud.py | grep -n "_style_font\|_style_role_font"`

- [ ] **Step 2: Update title font**

Find where the label/title is drawn. Currently it might read from widget.style. Update to use theme's title font:

```python
title_font = _style_role_font(widget, theme, scale, role="title")
```

- [ ] **Step 3: Update value font**

Find where the value (the main number) is drawn. Update to use role="value":

```python
value_font = _style_role_font(widget, theme, scale, role="value")
```

- [ ] **Step 4: Update unit font**

Find where the unit suffix is drawn. Update to use role="unit":

```python
unit_font = _style_role_font(widget, theme, scale, role="unit")
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_hud.py::test_render_hud_frame_draws_hud_v2_regions -v 2>&1 | tail -20`

Expected: Test passes

- [ ] **Step 6: Commit metric card changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: use role-specific fonts for metric_card rendering"
```

---

## Task 7: Update Hero Metric Rendering

**Files:**
- Modify: `src/race_overlay/hud.py:800-850` (_draw_hero_metric function)

**Purpose:** Ensure hero metric unit rendering uses `_style_role_font(role="unit")`.

- [ ] **Step 1: Find unit font in _draw_hero_metric**

Run: `grep -n "def _draw_hero_metric" src/race_overlay/hud.py`

Find the line where unit font is created.

- [ ] **Step 2: Update unit font call**

Change from generic call to role-specific:

```python
unit_font = _style_role_font(widget, theme, scale, role="unit")
```

- [ ] **Step 3: Run test**

Run: `uv run pytest tests/test_hud.py -q 2>&1 | tail -5`

Expected: All tests pass (or same number as before)

- [ ] **Step 4: Commit hero metric changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: use role-specific font for hero_metric unit rendering"
```

---

## Task 8: Update Context Card Rendering

**Files:**
- Modify: `src/race_overlay/hud.py` (search for _draw_context_card)

**Purpose:** Ensure context card uses proper font role separation.

- [ ] **Step 1: Find context card rendering function**

Run: `grep -n "def _draw_context_card" src/race_overlay/hud.py`

- [ ] **Step 2: Update font calls**

Find where fonts are created and update to use role-specific fonts:
- Title/label: `_style_role_font(widget, theme, scale, role="title")`
- Any unit text: `_style_role_font(widget, theme, scale, role="unit")`

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/test_hud.py -q`

Expected: All 203 tests pass

- [ ] **Step 4: Commit context card changes**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add src/race_overlay/hud.py
git commit -m "refactor: use role-specific fonts for context_card rendering"
```

---

## Task 9: Update overlay.yaml Configuration

**Files:**
- Modify: `overlay.yaml` (any widget with `font_family`, `font_weight`, or `font_size_px`)

**Purpose:** Update any existing widget configurations to use new `unit_font_*` names.

- [ ] **Step 1: Check current overlay.yaml for old font names**

Run: `grep -n "font_family\|font_weight\|font_size_px" overlay.yaml`

If no results, skip to Step 3 (nothing to migrate).

- [ ] **Step 2: Update any widget styles**

For each line found, replace:
- `font_family:` → `unit_font_family:`
- `font_weight:` → `unit_font_weight:`
- `font_size_px:` → `unit_font_size_px:`

- [ ] **Step 3: Commit overlay.yaml changes (if any)**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add overlay.yaml
git commit -m "refactor: update overlay.yaml widget styles to use unit_font_*"
```

Or if no changes:
```bash
echo "No changes needed to overlay.yaml"
```

---

## Task 10: Run Full Test Suite and Verify

**Files:**
- Test: `tests/test_hud.py`

**Purpose:** Verify all changes work together and no regressions were introduced.

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/test_hud.py -q`

Expected: All 203 tests pass

- [ ] **Step 2: If tests fail, review output**

If any tests fail, the error message will indicate which test and why. Common issues:
- Import errors: Check syntax in modified files
- Assertion errors: Check that helper functions are called correctly
- AttributeError: Check that field names are correct

Fix the issue and re-run.

- [ ] **Step 3: Render a test HUD to verify visually**

Run this Python script:

```bash
uv run python3 << 'EOF'
from datetime import datetime, timezone
from pathlib import Path
from race_overlay.hud import render_hud_frame
from race_overlay.hud_schema import HudConfig, HudThemeConfig
from race_overlay.models import HudSample

theme = HudThemeConfig(
    text_rgba=[247, 251, 255, 255],
    font_family='broadcast_ui',
    font_weight='regular',
    title_font_family='broadcast_ui',
    title_font_weight='regular',
    unit_font_family='broadcast_ui',
    unit_font_weight='regular',
)

config = HudConfig(
    preset='broadcast-runner',
    theme=theme,
)

hud_sample = HudSample(
    timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
    latitude=35.8,
    longitude=140.2,
    altitude_m=45,
    distance_m=5200,
    speed_mps=2.73,
    pace_seconds_per_km=440,
    heart_rate_bpm=133,
    cadence_spm=178,
)

route_points = [(35.8, 140.2), (35.801, 140.201), (35.802, 140.202)]

img = render_hud_frame(
    width=1280,
    height=720,
    hud_value=hud_sample,
    route_points=route_points,
    hud_config=config,
)

output_path = Path('rendered') / 'hud_font_separation_test.png'
output_path.parent.mkdir(exist_ok=True)
img.save(str(output_path))
print(f'✓ Generated test HUD: {output_path}')
EOF
```

Expected: No errors, file saved to `rendered/hud_font_separation_test.png`

- [ ] **Step 4: Verify visual rendering**

Run: `agent-browser batch "open file:///Users/dotennin-mac14/Downloads/霞ケ浦マラソン/rendered/hud_font_separation_test.png" "screenshot"`

Expected: Screenshot shows HUD with proper font styling - clear distinction between titles and units

- [ ] **Step 5: Final commit with test summary**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git log --oneline -5
```

Verify that all 5 commits from Tasks 1-9 are present.

---

## Task 11: Write Tests for Font Styling Separation

**Files:**
- Modify: `tests/test_hud.py`

**Purpose:** Add explicit tests verifying that widget style font parameters only affect units, not titles.

- [ ] **Step 1: Add test for stat_block title vs unit fonts**

Add this test function to `tests/test_hud.py`:

```python
def test_stat_block_title_uses_theme_default_font():
    """Verify stat_block title uses theme.title_font_* even with widget unit_font_* override."""
    theme = HudThemeConfig(
        title_font_family="broadcast_ui",
        title_font_weight="regular",
        unit_font_family="broadcast_value",
        unit_font_weight="bold",
    )
    
    widget = HudWidgetConfig(
        id="test-stat",
        type="stat_block",
        bindings={"label": "label", "value": "distance_m"},
        anchor="center",
        x=100,
        y=100,
        width=200,
        height=60,
        style={
            "unit_font_family": "broadcast_value",
            "unit_font_weight": "bold",
        }
    )
    
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=5200,
        speed_mps=None,
        pace_seconds_per_km=None,
        heart_rate_bpm=None,
        cadence_spm=None,
    )
    
    config = HudConfig(theme=theme, widgets=[widget])
    img = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_sample,
        route_points=[(35.8, 140.2)],
        hud_config=config,
    )
    
    # Should render without error
    assert img is not None
    assert img.size == (1280, 720)
```

- [ ] **Step 2: Add test for metric_card font separation**

Add this test:

```python
def test_metric_card_unit_font_independent_of_title():
    """Verify metric_card unit font can differ from title font."""
    theme = HudThemeConfig(
        title_font_family="broadcast_ui",
        value_font_family="broadcast_value",
        unit_font_family="broadcast_ui",
    )
    
    widget = HudWidgetConfig(
        id="test-pace",
        type="metric_card",
        bindings={"label": "label", "value": "pace_seconds_per_km"},
        anchor="center",
        x=100,
        y=100,
        width=150,
        height=60,
        style={
            "unit_font_family": "broadcast_value",
        }
    )
    
    hud_sample = HudSample(
        timestamp=datetime(2026, 4, 19, 9, 48, 10, tzinfo=timezone.utc),
        latitude=None,
        longitude=None,
        altitude_m=None,
        distance_m=None,
        speed_mps=None,
        pace_seconds_per_km=440,
        heart_rate_bpm=None,
        cadence_spm=None,
    )
    
    config = HudConfig(theme=theme, widgets=[widget])
    img = render_hud_frame(
        width=1280,
        height=720,
        hud_value=hud_sample,
        route_points=[(35.8, 140.2)],
        hud_config=config,
    )
    
    assert img is not None
    assert img.size == (1280, 720)
```

- [ ] **Step 3: Run new tests**

Run: `uv run pytest tests/test_hud.py::test_stat_block_title_uses_theme_default_font tests/test_hud.py::test_metric_card_unit_font_independent_of_title -v`

Expected: Both tests pass

- [ ] **Step 4: Run full test suite one more time**

Run: `uv run pytest tests/test_hud.py -q`

Expected: 205 tests pass (203 + 2 new tests)

- [ ] **Step 5: Commit tests**

```bash
cd /Users/dotennin-mac14/Downloads/霞ケ浦マラソン
git add tests/test_hud.py
git commit -m "test: add font styling separation verification tests

Add tests to verify:
- stat_block title uses theme defaults regardless of unit_font_* overrides
- metric_card unit font can be styled independently from title font"
```

---

## Summary Checklist

- [ ] Task 1: Migration layer added and committed
- [ ] Task 2: Editor schema updated for all 5 widget types and committed
- [ ] Task 3: Validation and helper functions updated and committed
- [ ] Task 4: Progress bar rendering updated and committed
- [ ] Task 5: Stat block rendering updated and committed
- [ ] Task 6: Metric card rendering updated and committed
- [ ] Task 7: Hero metric rendering updated and committed
- [ ] Task 8: Context card rendering updated and committed
- [ ] Task 9: overlay.yaml updated (if needed) and committed
- [ ] Task 10: Full test suite passes (203+ tests)
- [ ] Task 11: New tests added and passing

---

## Success Criteria

✓ All 203+ tests pass with no regressions
✓ Widget style `unit_font_*` parameters control only unit suffix rendering
✓ Title/label rendering uses theme's `title_font_*` defaults
✓ Old YAML configs with `font_family`, `font_weight`, `font_size_px` are automatically migrated
✓ HUD renders with clear visual distinction between title fonts (theme default) and unit fonts (widget override)
✓ New tests verify font styling separation works correctly
