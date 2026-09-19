"""
IC-Pi Unit Validation Service
==============================
Validates raw KPI values against the KPI's declared unit_type.
The platform, not the consultant's eyesight, catches contradictory data.

unit_type is the machine-readable enum emitted by the formula generator:
percent, ratio, duration, currency, count, score, rate.
The human-readable `unit` label may be in any language; never parse it.

Returns (errors, warnings):
  errors   = impossible values. Refuse to save.
  warnings = suspicious values. Save, but make the consultant acknowledge.
"""

PROVENANCE_TAGS = {"standard", "regulation", "ai", "expert", "n/a", ""}

VALID_UNIT_TYPES = {
    "percent", "ratio", "duration", "currency", "count", "score", "rate",
}


def unit_is_usable(unit, unit_type):
    """A KPI cannot be scored if its unit is missing or is a provenance tag."""
    u = (unit or "").strip().lower()
    ut = (unit_type or "").strip().lower()
    if u in PROVENANCE_TAGS and ut not in VALID_UNIT_TYPES:
        return False
    return True


def validate_value(label, value, unit, unit_type, tau_floor=None,
                   best_value=None, worst_value=None):
    """
    Validate one raw value. `label` is the KPI name, used in messages.
    """
    errors = []
    warnings = []

    ut = (unit_type or "").strip().lower()
    shown_unit = (unit or "").strip()

    # --- Hard rules: physically impossible for the declared type ---

    if ut == "percent":
        if value < 0 or value > 100:
            errors.append(
                label + ": " + str(value) + " is outside 0-100 and the unit is "
                + (shown_unit or "percent") + "."
            )
        elif 0 < value < 1:
            warnings.append(
                label + ": " + str(value) + " looks like a ratio, not a percentage. "
                "Did you mean " + str(round(value * 100, 1)) + "?"
            )

    elif ut == "ratio":
        if value < 0 or value > 1:
            errors.append(
                label + ": " + str(value) + " is outside 0-1 and the unit is a ratio."
            )
        elif value > 1:
            warnings.append(
                label + ": " + str(value) + " looks like a percentage, not a ratio."
            )

    elif ut == "duration":
        if value < 0:
            errors.append(label + ": a duration cannot be negative.")

    elif ut == "currency":
        if value < 0:
            warnings.append(
                label + ": negative cost. Confirm this is a credit, not a typo."
            )

    elif ut == "count":
        if value < 0:
            errors.append(label + ": a count cannot be negative.")
        elif value != int(value):
            warnings.append(
                label + ": " + str(value) + " is not a whole number but the unit is a count."
            )

    # --- Unit-agnostic rules: work for every type, including unknown ones ---

    # Order-of-magnitude check against the tau floor.
    if tau_floor is not None and value != 0 and tau_floor != 0:
        ratio = abs(value) / abs(tau_floor)
        if ratio > 100 or ratio < 0.01:
            warnings.append(
                label + ": " + str(value) + " is far from its floor of " + str(tau_floor)
                + (" " + shown_unit if shown_unit else "")
                + ". Check the unit before accepting."
            )

    # The value should sit inside the range the consultant declared.
    if best_value is not None and worst_value is not None:
        low = min(best_value, worst_value)
        high = max(best_value, worst_value)
        span = high - low
        if span > 0 and (value < low - span or value > high + span):
            warnings.append(
                label + ": " + str(value) + " falls well outside the declared range "
                + str(low) + " to " + str(high) + "."
            )

    return errors, warnings
