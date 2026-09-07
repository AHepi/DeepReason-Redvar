"""Operator policy (spec Parts IV–VII), independent of generated language.

All numerical defaults are engineering settings, not definitions of creativity.
Only the operator API accepts policy updates; a proposal is never fed here.
"""

from copy import deepcopy
from pathlib import Path
import tomllib


DEFAULTS = {
    "run_profile": "creative", "history": "profile_default",
    "participant_history": "selected", "attention_learning": "off",
    "commitment_actions": "registered", "input_tokens": 8192,
    "generated_tokens": 1024, "neighbour_depth": 1, "neighbour_items": 6,
    "neighbour_tokens": 3072, "edge_inspections": 64,
    "attention_note_tokens": 512, "work_before_review": 6, "trial_calls": 2,
    "attention_review_every": 2, "nonlocal_every": 6,
    "mediation_calls_per_cycle": 1, "run_model_calls": 24,
    "run_token_volume": 262144, "inflight_calls": 1,
    "checker_slices_per_boundary": 4, "checker_slice_bytes": 65536,
    "conditional_bindings_per_account": 16, "strict_tokens": True,
    "timeout_seconds": 120, "max_pending_trials": 4, "roots_limit": 8,
    "required_limit": 16, "read_page_chars": 4000, "max_read_pages": 4,
    "dependency_slice": 64, "history_limit": 256,
    "max_source_bytes": 16777216, "max_collection_bytes": 134217728,
    "jolt_echo": False, "jolt_cooldown": 6, "daydreaming": True,
    "recipes": {"local": {"neighbour_depth": 1, "neighbour_items": 6},
                "broader": {"neighbour_depth": 2, "neighbour_items": 10}},
}

ENUMS = {
    "run_profile": {"creative", "research"},
    "history": {"profile_default", "off", "bounded", "append-only"},
    "participant_history": {"off", "selected"},
    "attention_learning": {"off", "observe", "on"},
    "commitment_actions": {"off", "registered"},
}


def validate(overrides=None):
    """Return a fresh validated policy; reject misspellings and inert controls."""
    policy = deepcopy(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise ValueError("Unknown policy setting(s): " + ", ".join(sorted(unknown)))
        policy.update(deepcopy(overrides))
    for key, options in ENUMS.items():
        if policy[key] not in options:
            raise ValueError(f"{key} must be one of {', '.join(sorted(options))}")
    zero_allowed = {"neighbour_depth", "neighbour_items", "neighbour_tokens",
                    "edge_inspections", "mediation_calls_per_cycle"}
    for key, default in DEFAULTS.items():
        value = policy[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
        elif isinstance(default, int):
            if type(value) is not int or value < (0 if key in zero_allowed else 1):
                raise ValueError(f"{key} must be a {'nonnegative' if key in zero_allowed else 'positive'} integer")
    if policy["inflight_calls"] != 1:
        raise ValueError("This sequential implementation supports inflight_calls = 1")
    if policy["mediation_calls_per_cycle"] > 1:
        raise ValueError("The baseline permits at most one shared mediation per cycle")
    if policy["neighbour_tokens"] > policy["input_tokens"]:
        raise ValueError("neighbour_tokens must fit inside input_tokens")
    if policy["roots_limit"] > 8 or policy["required_limit"] > 16:
        raise ValueError("Root and required-address packets must be paged at 8 and 16")
    recipes = policy["recipes"]
    if not isinstance(recipes, dict) or "local" not in recipes or len(recipes) > 16:
        raise ValueError("recipes needs a local recipe and at most 16 entries")
    for name, recipe in recipes.items():
        if not isinstance(name, str) or not isinstance(recipe, dict):
            raise ValueError("Each named recipe must be a table")
        if set(recipe) - {"neighbour_depth", "neighbour_items"}:
            raise ValueError("Recipes can change only neighbour_depth and neighbour_items")
        for value in recipe.values():
            if type(value) is not int or value < 0:
                raise ValueError("Recipe limits must be nonnegative integers")
    return policy


def load_policy(path):
    with Path(path).open("rb") as file:
        return validate(tomllib.load(file))


def effective_history(policy):
    setting = policy["history"]
    if setting == "profile_default":
        return "append-only" if policy["run_profile"] == "research" else "off"
    return setting


def default_toml():
    lines = ["# Operator configuration; prose cannot change these permissions."]
    for key, value in DEFAULTS.items():
        if key == "recipes":
            continue
        literal = ('true' if value else 'false') if isinstance(value, bool) else repr(value)
        lines.append(f"{key} = {literal}")
    for name, recipe in DEFAULTS["recipes"].items():
        lines.extend(["", f"[recipes.{name}]"])
        lines.extend(f"{key} = {value}" for key, value in recipe.items())
    return "\n".join(lines) + "\n"
