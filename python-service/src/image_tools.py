from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from models import default_character_entry, default_draft, default_opening_entry, default_world_book_entry, merge_defaults

ALLOWED_POSITIONS = {
    "before_char",
    "after_char",
    "before_example",
    "after_example",
    "top_an",
    "bottom_an",
    "at_depth",
}


def ensure_png(source_path: str, output_path: str) -> str:
    source = Path(source_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        rgba.save(target, format="PNG")
    return str(target)


def _split_keywords(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _replace_role_name_with_user(text: str, role_name: str) -> str:
    source = str(text or "")
    target = str(role_name or "").strip()
    if not source or not target:
        return source
    return source.replace(target, "{{user}}")


def _project_user_role_character(character: dict[str, Any]) -> dict[str, Any]:
    if not bool(character.get("isUserRole", False)):
        return character
    projected = dict(character)
    original_name = str(character.get("name", "")).strip()
    projected["name"] = "{{user}}"
    projected["triggerMode"] = "always"
    projected["triggerKeywords"] = ["{{user}}", "玩家", "你"]
    projected["speakingExample"] = _replace_role_name_with_user(str(character.get("speakingExample", "")), original_name)
    return projected


def _character_to_lore_content(character: dict[str, Any]) -> str:
    parts = [
        f"姓名: {character.get('name', '').strip()}",
        f"年龄: {character.get('age', '').strip()}",
        f"外貌: {character.get('appearance', '').strip()}",
        f"性格: {character.get('personality', '').strip()}",
        f"说话方式: {character.get('speakingStyle', '').strip()}",
        f"说话示例: {character.get('speakingExample', '').strip()}",
        f"背景: {character.get('background', '').strip()}",
    ]
    return "\n".join(part for part in parts if not part.endswith(": "))


def _map_position(position: str) -> str:
    if position in {"before_char", "after_char"}:
        return position
    return "after_char"


def _entry_probability(entry: dict[str, Any]) -> int:
    advanced = entry.get("advanced", {})
    value = advanced.get("triggerProbability", 100)
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 100
    return max(0, min(100, number))


def _entry_depth(entry: dict[str, Any]) -> int:
    advanced = entry.get("advanced", {})
    value = advanced.get("depth", 4)
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 4
    return max(0, number)


def _entry_order(entry: dict[str, Any]) -> int:
    advanced = entry.get("advanced", {})
    value = advanced.get("insertionOrder", 200)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 200


def _character_to_book_entry(character: dict[str, Any]) -> dict[str, Any]:
    keywords = [item.strip() for item in character.get("triggerKeywords", []) if item.strip()]
    if not keywords and character.get("name", "").strip():
        keywords = [character["name"].strip()]
    trigger_mode = "always" if character.get("triggerMode") == "always" else "keyword"
    position = character.get("advanced", {}).get("insertionPosition", "after_char")
    return {
        "keys": keywords,
        "content": _character_to_lore_content(character),
        "extensions": {
            "roleplaycard": {
                "entryType": "character",
                "sourceId": character.get("id"),
                "isUserRole": bool(character.get("isUserRole", False)),
                "triggerMode": trigger_mode,
                "triggerProbability": _entry_probability(character),
                "insertionPosition": position,
                "depth": _entry_depth(character),
            }
        },
        "enabled": bool(character.get("enabled", True)),
        "insertion_order": _entry_order(character),
        "comment": character.get("name", ""),
        "case_sensitive": False,
        "selective": False,
        "secondary_keys": [],
        "constant": trigger_mode == "always",
        "position": _map_position(position),
        "probability": _entry_probability(character),
        "depth": _entry_depth(character),
    }


def _world_entry_to_book_entry(entry: dict[str, Any]) -> dict[str, Any]:
    keywords = [item.strip() for item in entry.get("keywords", []) if item.strip()]
    trigger_mode = "always" if entry.get("triggerMode") == "always" else "keyword"
    position = entry.get("advanced", {}).get("insertionPosition", "after_char")
    return {
        "keys": keywords,
        "content": entry.get("content", ""),
        "extensions": {
            "roleplaycard": {
                "entryType": "worldbook",
                "sourceId": entry.get("id"),
                "triggerMode": trigger_mode,
                "triggerProbability": _entry_probability(entry),
                "insertionPosition": position,
                "depth": _entry_depth(entry),
            }
        },
        "enabled": bool(entry.get("enabled", True)),
        "insertion_order": _entry_order(entry),
        "comment": entry.get("title", ""),
        "case_sensitive": False,
        "selective": False,
        "secondary_keys": [],
        "constant": trigger_mode == "always",
        "position": _map_position(position),
        "probability": _entry_probability(entry),
        "depth": _entry_depth(entry),
    }


def _build_character_book(draft: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for character in draft.get("characters", []):
        if character.get("name", "").strip():
            entries.append(_character_to_book_entry(_project_user_role_character(character)))
    for entry in draft.get("worldBook", {}).get("entries", []):
        if entry.get("content", "").strip():
            entries.append(_world_entry_to_book_entry(entry))

    return {
        "name": draft.get("card", {}).get("name", ""),
        "description": draft.get("card", {}).get("description", ""),
        "scan_depth": 4,
        "token_budget": 1200,
        "recursive_scanning": True,
        "extensions": {"roleplaycard": {"schemaVersion": "0.0.2"}},
        "entries": entries,
    }


def draft_to_tavern_character(draft: dict[str, Any]) -> dict[str, Any]:
    characters = draft.get("characters", [])
    npc_candidates = [item for item in characters if not bool(item.get("isUserRole", False))]
    primary = npc_candidates[0] if npc_candidates else (characters[0] if characters else {})
    openings = draft.get("openings", [])
    if not isinstance(openings, list):
        openings = []
    if not openings and isinstance(draft.get("opening"), dict):
        openings = [draft["opening"]]
    primary_opening = openings[0] if openings and isinstance(openings[0], dict) else default_opening_entry()
    alternate_greetings = []
    for item in openings[1:]:
        if not isinstance(item, dict):
            continue
        first_message = str(item.get("firstMessage", "")).strip()
        if first_message:
            alternate_greetings.append(first_message)
    if not alternate_greetings:
        legacy_greeting = str(primary_opening.get("greeting", "")).strip()
        if legacy_greeting:
            alternate_greetings.append(legacy_greeting)
    card = draft.get("card", {})
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": card.get("name", "") or primary.get("name", ""),
            "description": primary.get("appearance", ""),
            "personality": primary.get("personality", ""),
            "scenario": primary_opening.get("scenario", ""),
            "first_mes": primary_opening.get("firstMessage", ""),
            "mes_example": primary_opening.get("exampleDialogue", "") or primary.get("speakingExample", ""),
            "creator_notes": card.get("description", ""),
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": alternate_greetings,
            "tags": ["RolePlayCard", "multi-character"],
            "creator": "RolePlayCard",
            "character_version": "0.0.2",
            "extensions": {
                "roleplaycard": {
                    "cardId": draft.get("id"),
                    "characterCount": len(characters),
                }
            },
            "character_book": _build_character_book(draft),
        },
    }


def embed_tavern_metadata(source_png: str, draft: dict[str, Any], output_path: str) -> str:
    character_payload = draft_to_tavern_character(draft)
    chara = base64.b64encode(json.dumps(character_payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    pnginfo = PngInfo()
    pnginfo.add_text("chara", chara)
    pnginfo.add_text("roleplaycard", json.dumps(draft, ensure_ascii=False))
    with Image.open(source_png) as image:
        image.save(output_path, format="PNG", pnginfo=pnginfo)
    return output_path


def _safe_json_load(raw: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


def _read_card_payload(input_path: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    path = Path(input_path)
    if path.suffix.lower() == ".png":
        with Image.open(path) as image:
            embedded = image.text
            raw_roleplaycard = embedded.get("roleplaycard", "")
            raw_chara = embedded.get("chara", "")
            raw_ccv3 = embedded.get("ccv3", "")
        roleplaycard_payload = _safe_json_load(raw_roleplaycard) if raw_roleplaycard else None
        chara_payload = None
        if raw_chara or raw_ccv3:
            candidate = raw_chara or raw_ccv3
            try:
                decoded = base64.b64decode(candidate).decode("utf-8", errors="ignore")
                chara_payload = _safe_json_load(decoded)
            except (ValueError, UnicodeDecodeError):
                chara_payload = None
        return roleplaycard_payload, chara_payload

    raw = path.read_text(encoding="utf-8")
    payload = _safe_json_load(raw)
    if payload and "spec" in payload:
        return None, payload
    return payload, None


def _extract_data_section(payload: dict[str, Any]) -> dict[str, Any]:
    spec = str(payload.get("spec", "")).strip().lower()
    if spec.startswith("chara_card_v") and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload.get("data"), dict):
        # Some exporters omit/alter spec but still wrap in `data`.
        return payload["data"]
    return payload


def _entry_to_world_book(entry: dict[str, Any]) -> dict[str, Any]:
    world_entry = default_world_book_entry()
    world_entry["title"] = (
        str(entry.get("comment", "")).strip()
        or str(entry.get("name", "")).strip()
        or str(entry.get("title", "")).strip()
    )
    keys = entry.get("keys", entry.get("key", entry.get("keywords", [])))
    if isinstance(keys, list):
        world_entry["keywords"] = [str(item).strip() for item in keys if str(item).strip()]
    elif isinstance(keys, str):
        world_entry["keywords"] = _split_keywords(keys)
    world_entry["content"] = str(
        entry.get("content", entry.get("text", entry.get("value", entry.get("entry", ""))))
    )
    world_entry["enabled"] = bool(entry.get("enabled", True))
    world_entry["triggerMode"] = "always" if entry.get("constant", False) else "keyword"

    advanced = world_entry["advanced"]
    try:
        advanced["insertionOrder"] = int(entry.get("insertion_order", advanced["insertionOrder"]))
    except (TypeError, ValueError):
        pass
    try:
        advanced["triggerProbability"] = int(entry.get("probability", advanced["triggerProbability"]))
    except (TypeError, ValueError):
        pass
    position = str(entry.get("position", advanced["insertionPosition"]))
    advanced["insertionPosition"] = position if position in ALLOWED_POSITIONS else "after_char"
    try:
        advanced["depth"] = int(entry.get("depth", advanced["depth"]))
    except (TypeError, ValueError):
        pass

    extensions = entry.get("extensions", {})
    if isinstance(extensions, dict):
        rp_ext = extensions.get("roleplaycard", {})
        if isinstance(rp_ext, dict):
            try:
                advanced["triggerProbability"] = int(rp_ext.get("triggerProbability", advanced["triggerProbability"]))
            except (TypeError, ValueError):
                pass
            try:
                advanced["depth"] = int(rp_ext.get("depth", advanced["depth"]))
            except (TypeError, ValueError):
                pass
            position = str(rp_ext.get("insertionPosition", advanced["insertionPosition"]))
            advanced["insertionPosition"] = position if position in ALLOWED_POSITIONS else advanced["insertionPosition"]

    return world_entry


def tavern_payload_to_draft(payload: dict[str, Any], source_path: str) -> dict[str, Any]:
    data = _extract_data_section(payload)
    draft = default_draft()

    draft["card"]["name"] = data.get("name", "")
    draft["card"]["description"] = data.get("creator_notes", "")
    scenario = str(data.get("scenario", ""))
    first_message = str(data.get("first_mes", ""))
    example_dialogue = str(data.get("mes_example", ""))

    openings = []
    primary_opening = default_opening_entry()
    primary_opening["title"] = "首屏 1"
    primary_opening["scenario"] = scenario
    primary_opening["firstMessage"] = first_message
    primary_opening["exampleDialogue"] = example_dialogue
    openings.append(primary_opening)

    alternate = data.get("alternate_greetings", [])
    if isinstance(alternate, list):
        for index, item in enumerate(alternate, start=2):
            message = str(item).strip()
            if not message:
                continue
            alt_opening = default_opening_entry()
            alt_opening["title"] = f"首屏 {index}"
            alt_opening["scenario"] = scenario
            alt_opening["firstMessage"] = message
            alt_opening["exampleDialogue"] = example_dialogue
            openings.append(alt_opening)
    draft["openings"] = openings
    draft["opening"] = openings[0]

    # External cards can carry different character schemas; keep Role section empty
    # and import canonical lorebook entries into worldBook instead.
    draft["characters"] = [default_character_entry()]

    book = data.get("character_book", data.get("lorebook", {}))
    entries = []
    if isinstance(book, dict):
        raw_entries = book.get("entries", [])
        if isinstance(raw_entries, list):
            entries = [_entry_to_world_book(entry) for entry in raw_entries if isinstance(entry, dict)]
        elif isinstance(raw_entries, dict):
            entries = [_entry_to_world_book(entry) for entry in raw_entries.values() if isinstance(entry, dict)]
    draft["worldBook"]["entries"] = entries

    path = Path(source_path)
    if path.suffix.lower() == ".png":
        draft["illustration"]["originalImagePath"] = str(path)
        draft["illustration"]["generatedImagePath"] = ""
        draft["illustration"]["exportImagePath"] = str(path)

    return merge_defaults(default_draft(), draft)


def import_character_card(input_path: str) -> dict[str, Any]:
    roleplaycard_payload, chara_payload = _read_card_payload(input_path)
    if roleplaycard_payload:
        draft = merge_defaults(default_draft(), roleplaycard_payload)
        draft["__importSource"] = "roleplaycard"
        return draft
    if chara_payload:
        draft = tavern_payload_to_draft(chara_payload, input_path)
        draft["__importSource"] = "external"
        return draft
    raise ValueError("未在文件中检测到可用的角色卡数据（roleplaycard/chara）。")
