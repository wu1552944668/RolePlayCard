from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from image_tools import embed_tavern_metadata, ensure_png, import_character_card
from models import (
    default_character_entry,
    default_opening_entry,
    default_settings,
    default_timeline,
    default_world_book_entry,
    merge_defaults,
    normalize_draft,
)
from prompts import (
    build_character_from_story_prompt,
    build_field_prompt,
    build_image_prompt,
    build_plot_progression_prompt,
    build_story_outline_prompt,
)
from providers import ProviderRegistry
from storage import AppStorage


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "error_code": None, "message": message, "data": data}


def fail(message: str, error_code: str = "error") -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "message": message, "data": None}


def _safe_filename(base: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", base).strip()
    return cleaned or "character-card"


def _primary_opening(draft: dict[str, Any]) -> dict[str, Any]:
    openings = draft.get("openings", [])
    if isinstance(openings, list):
        for item in openings:
            if isinstance(item, dict):
                return item
    opening = draft.get("opening", {})
    return opening if isinstance(opening, dict) else {}


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "")
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _split_keywords(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = re.split(r"[,\n，]", str(raw or ""))
    return [item for item in values if item]


class RolePlayCardService:
    def __init__(self, app_data_dir: str):
        self.storage = AppStorage(app_data_dir)
        self.providers = ProviderRegistry()
        self.imports_dir = self.storage.base_dir / "imports"
        self.exports_dir = self.storage.base_dir / "exports"
        self.text_prefix_prompts_dir = Path(__file__).resolve().parents[2] / "jailbreak-prompts"
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.text_prefix_prompts_dir.mkdir(parents=True, exist_ok=True)

    def _load_builtin_prefix_prompts(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for path in sorted(self.text_prefix_prompts_dir.glob("*.txt"), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            model = path.stem
            if not model:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="ignore")
            entries.append(
                {
                    "model": model,
                    "filename": path.name,
                    "content": content,
                }
            )
        return entries

    def _resolve_text_prefix_prompt(self, config: dict[str, Any]) -> str:
        custom_prompt = str(config.get("prefixPrompt", ""))
        mode = str(config.get("prefixPromptMode", "custom")).lower()
        if mode != "builtin":
            return custom_prompt
        candidate = str(config.get("builtinPrefixPromptModel", "")) or str(config.get("model", ""))
        if not candidate:
            return custom_prompt
        by_model = {item["model"].casefold(): item for item in self._load_builtin_prefix_prompts()}
        matched = by_model.get(candidate.casefold())
        if matched is None:
            return custom_prompt
        builtin_prompt = str(matched.get("content", ""))
        return builtin_prompt or custom_prompt

    def _resolve_text_generation_config(self, config: dict[str, Any]) -> dict[str, Any]:
        resolved = dict(config)
        resolved["prefixPrompt"] = self._resolve_text_prefix_prompt(config)
        return resolved

    def _extract_plot_nodes(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        raw_progression = outline.get("plotProgression", outline.get("plot_progression"))
        raw_nodes: Any = []
        if isinstance(raw_progression, dict):
            raw_nodes = raw_progression.get("nodes", [])
        elif isinstance(raw_progression, list):
            raw_nodes = raw_progression
        elif isinstance(outline.get("plotNodes"), list):
            raw_nodes = outline.get("plotNodes", [])

        nodes: list[dict[str, Any]] = []
        if not isinstance(raw_nodes, list):
            return nodes
        used_ids: set[str] = set()
        for index, item in enumerate(raw_nodes[:12], start=1):
            if not isinstance(item, dict):
                continue
            base_id = str(item.get("id", item.get("nodeId", item.get("key", "")))).strip()
            if not base_id:
                base_id = f"n{index}"
            node_id = base_id
            suffix = 2
            while node_id in used_ids:
                node_id = f"{base_id}_{suffix}"
                suffix += 1
            used_ids.add(node_id)

            node = {
                "id": node_id,
                "title": str(item.get("title", item.get("name", item.get("stage", "")))),
                "timePoint": str(item.get("timePoint", item.get("time", item.get("timeline", "")))),
                "trigger": str(item.get("trigger", item.get("triggerCondition", item.get("condition", "")))),
                "event": str(item.get("event", item.get("keyEvent", item.get("summary", "")))),
                "objective": str(item.get("objective", item.get("goal", ""))),
                "conflict": str(item.get("conflict", item.get("obstacle", ""))),
                "outcome": str(item.get("outcome", item.get("result", ""))),
                "nextHook": str(item.get("nextHook", item.get("next", item.get("nextStep", "")))),
                "parentId": "",
                "_parentRef": str(
                    item.get("parentId", item.get("parentNodeId", item.get("parentTitle", item.get("parent", ""))))
                ).strip(),
            }
            if not any(
                [
                    node["title"],
                    node["timePoint"],
                    node["trigger"],
                    node["event"],
                    node["objective"],
                    node["conflict"],
                    node["outcome"],
                    node["nextHook"],
                ]
            ):
                continue
            if not node["title"]:
                node["title"] = f"节点 {len(nodes) + 1}"
            nodes.append(node)

        id_map = {str(node["id"]): str(node["id"]) for node in nodes}
        title_map = {str(node["title"]): str(node["id"]) for node in nodes if str(node.get("title", ""))}
        for node in nodes:
            parent_ref = str(node.pop("_parentRef", "")).strip()
            if not parent_ref:
                node["parentId"] = ""
                continue
            resolved_parent = ""
            if parent_ref in id_map:
                resolved_parent = id_map[parent_ref]
            elif parent_ref in title_map:
                resolved_parent = title_map[parent_ref]
            if resolved_parent == str(node["id"]):
                resolved_parent = ""
            node["parentId"] = resolved_parent
        return nodes

    def _enforce_progression_parenting(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not nodes:
            return []

        normalized_nodes: list[dict[str, Any]] = []
        for index, item in enumerate(nodes, start=1):
            node = dict(item)
            node_id = str(node.get("id", "")).strip() or f"n{index}"
            node["id"] = node_id
            node["parentId"] = ""
            normalized_nodes.append(node)

        groups: list[list[int]] = []
        last_key = ""
        for idx, node in enumerate(normalized_nodes):
            raw_time = str(node.get("timePoint", "")).strip()
            key = re.sub(r"\s+", " ", raw_time.casefold()) if raw_time else f"__index_{idx}"
            if groups and key == last_key:
                groups[-1].append(idx)
            else:
                groups.append([idx])
                last_key = key

        if not groups:
            return normalized_nodes

        root_idx = groups[0][0]
        root_id = str(normalized_nodes[root_idx]["id"])
        normalized_nodes[root_idx]["parentId"] = ""
        mainline_parent_id = root_id

        for idx in groups[0][1:]:
            node_id = str(normalized_nodes[idx]["id"])
            normalized_nodes[idx]["parentId"] = "" if node_id == root_id else root_id

        for group in groups[1:]:
            if len(group) == 1:
                idx = group[0]
                node_id = str(normalized_nodes[idx]["id"])
                normalized_nodes[idx]["parentId"] = "" if node_id == mainline_parent_id else mainline_parent_id
                mainline_parent_id = node_id
                continue

            for idx in group:
                node_id = str(normalized_nodes[idx]["id"])
                normalized_nodes[idx]["parentId"] = "" if node_id == mainline_parent_id else mainline_parent_id
            mainline_parent_id = str(normalized_nodes[group[0]]["id"])

        return normalized_nodes

    def _fallback_plot_nodes(
        self,
        story_summary: str,
        openings: list[dict[str, Any]],
        locations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        first_opening = openings[0] if openings else {}
        first_location = locations[0] if locations else {}
        second_location = locations[1] if len(locations) > 1 else first_location
        summary = story_summary or "围绕关键人物与核心地点展开的剧情。"
        return [
            {
                "title": "起点建立",
                "timePoint": "故事开端",
                "trigger": "玩家进入故事场景并与关键角色接触",
                "event": summary[:140],
                "objective": "明确主线目标与主要人物关系",
                "conflict": "信息不足或彼此不信任",
                "outcome": "获得第一批线索",
                "nextHook": str(first_opening.get("title", "")) or str(first_location.get("title", "")),
                "parentId": "",
            },
            {
                "title": "中段推进",
                "timePoint": "调查/行动中段",
                "trigger": "第一批线索被验证或遭遇阻碍",
                "event": f"围绕地点 {str(first_location.get('title', '关键地点 A'))} 深挖隐藏信息。",
                "objective": "锁定关键矛盾与对立面",
                "conflict": "误导信息、资源受限或外部压力",
                "outcome": "主线从探索转入对抗",
                "nextHook": str(second_location.get("title", "")) or "更深层真相节点",
                "parentId": "",
            },
            {
                "title": "终局走向",
                "timePoint": "后段/收束阶段",
                "trigger": "关键证据或关键人物态度发生变化",
                "event": "主角方对核心冲突发起决断行动。",
                "objective": "解决核心冲突并形成阶段性结论",
                "conflict": "最终抉择代价与立场冲突",
                "outcome": "形成可持续展开的后续剧情方向",
                "nextHook": "引出后续支线或下一阶段主线",
                "parentId": "",
            },
        ]

    def _build_plot_progression_content(self, nodes: list[dict[str, Any]]) -> str:
        payload = {
            "guidanceType": "plot_progression",
            "version": "1.0",
            "usage": "按 nodes 顺序推进主线；可根据玩家行为在当前节点内进行分支调整。",
            "nodes": nodes,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_plot_progression_timeline(
        self,
        progression_payload: dict[str, Any] | None,
        outline: dict[str, Any],
        story_summary: str,
        openings: list[dict[str, Any]],
        locations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        if isinstance(progression_payload, dict):
            nodes = self._extract_plot_nodes(progression_payload)
        if not nodes:
            nodes = self._extract_plot_nodes(outline)
        if not nodes:
            nodes = self._fallback_plot_nodes(story_summary, openings, locations)
        timeline = merge_defaults(default_timeline(), {})
        timeline["nodes"] = self._enforce_progression_parenting(nodes)
        return timeline

    def _build_plot_progression_world_entry(self, timeline: dict[str, Any]) -> dict[str, Any]:
        normalized_timeline = merge_defaults(default_timeline(), timeline if isinstance(timeline, dict) else {})
        nodes = normalized_timeline.get("nodes", [])
        if not isinstance(nodes, list):
            nodes = []
        content = self._build_plot_progression_content(nodes)
        entry = merge_defaults(default_world_book_entry(), {})
        entry["enabled"] = bool(normalized_timeline.get("enabled", False))
        entry["triggerMode"] = "always"
        entry["title"] = str(normalized_timeline.get("title", "剧情推进")) or "剧情推进"
        keywords = normalized_timeline.get("keywords", [])
        if isinstance(keywords, list):
            entry["keywords"] = [str(item) for item in keywords if str(item)]
        else:
            entry["keywords"] = ["剧情推进", "主线节点", "剧情走向"]
        if not entry["keywords"]:
            entry["keywords"] = ["剧情推进", "主线节点", "剧情走向"]
        entry["content"] = content
        return entry

    def _build_export_draft_with_timeline_entry(self, draft: dict[str, Any]) -> dict[str, Any]:
        export_draft = json.loads(json.dumps(draft, ensure_ascii=False))
        world_book = export_draft.get("worldBook", {})
        existing_entries = world_book.get("entries", []) if isinstance(world_book, dict) else []
        filtered_entries: list[dict[str, Any]] = []
        if isinstance(existing_entries, list):
            filtered_entries = [
                entry
                for entry in existing_entries
                if isinstance(entry, dict) and str(entry.get("title", "")).strip() != "剧情推进"
            ]

        timeline_entry = self._build_plot_progression_world_entry(export_draft.get("timeline", {}))
        filtered_entries.append(timeline_entry)
        export_draft.setdefault("worldBook", {})
        export_draft["worldBook"]["entries"] = filtered_entries
        return export_draft

    def _settings_from_payload(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload and isinstance(payload.get("settings"), dict):
            return merge_defaults(default_settings(), payload["settings"])
        return default_settings()

    def get_settings(self) -> dict[str, Any]:
        return ok(default_settings())

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = merge_defaults(default_settings(), settings)
        return ok(merged, "Settings accepted. Persist this in browser cookie.")

    def list_text_prefix_prompts(self) -> dict[str, Any]:
        entries = self._load_builtin_prefix_prompts()
        items = [{"model": item["model"], "filename": item["filename"]} for item in entries]
        return ok({"directory": str(self.text_prefix_prompts_dir), "items": items})

    def test_settings(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        results = []
        for key, getter in (
            ("textProvider", self.providers.get_text_provider),
            ("imageProvider", self.providers.get_image_provider),
        ):
            config = settings[key]
            try:
                provider = getter(config["provider"])
                valid, detail = provider.validate(config)
            except KeyError:
                valid, detail = False, f"unsupported provider: {config.get('provider')}"
            results.append({"provider": config["provider"], "ok": valid, "detail": detail})
        return ok(results)

    def test_text_provider(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["textProvider"]
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            models = provider.list_models(config)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_model_list_failed")
        return ok({"provider": config["provider"], "detail": detail, "models": models}, "Text provider connected.")

    def test_image_provider(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["imageProvider"]
        try:
            provider = self.providers.get_image_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            models = provider.list_models(config)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_model_list_failed")
        return ok({"provider": config["provider"], "detail": detail, "models": models}, "Image provider connected.")

    def list_drafts(self) -> dict[str, Any]:
        return ok(self.storage.list_drafts())

    def clear_all_data(self) -> dict[str, Any]:
        result = self.storage.clear_all_data()
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        return ok(result, "All stored data cleared.")

    def load_draft(self, draft_id: str) -> dict[str, Any]:
        try:
            return ok(self.storage.load_draft(draft_id))
        except FileNotFoundError as exc:
            return fail(str(exc), "draft_not_found")

    def save_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = normalize_draft(payload["draft"])
        return ok(self.storage.save_draft(draft, save_as=payload.get("saveAs", False)), "Draft saved.")

    def generate_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["textProvider"]
        if not str(config.get("model", "")):
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        draft = normalize_draft(payload["draft"])
        prompt = build_field_prompt(payload["field"], payload["mode"], payload.get("userInput", ""), draft)
        runtime_config = self._resolve_text_generation_config(config)
        try:
            generated = provider.generate(runtime_config, prompt)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"field": payload["field"], "result": generated, "promptPreview": prompt}, "Field generated.")

    def generate_card_from_story(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = dict(settings["textProvider"])
        if not str(config.get("model", "")):
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        runtime_config = self._resolve_text_generation_config(config)

        story_text = str(payload.get("storyText", ""))
        if not story_text:
            return fail("storyText is required", "validation_error")

        draft = normalize_draft(payload["draft"])
        outline_prompt = build_story_outline_prompt(story_text, draft)
        try:
            generated_outline = provider.generate(runtime_config, outline_prompt)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")

        outline = _extract_json_object(generated_outline)
        if not outline:
            return fail("模型返回非 JSON，无法解析。", "provider_generation_failed")

        story_summary = str(outline.get("storySummary", ""))

        card = outline.get("card", {})
        if isinstance(card, dict):
            draft["card"]["name"] = str(card.get("name", draft["card"]["name"]))
            draft["card"]["description"] = str(card.get("description", draft["card"]["description"]))

        raw_character_seeds = outline.get("characters", [])
        character_seeds: list[dict[str, Any]] = []
        if isinstance(raw_character_seeds, list):
            for item in raw_character_seeds:
                if not isinstance(item, dict):
                    continue
                seed_name = str(item.get("name", ""))
                if not seed_name:
                    continue
                character_seeds.append(
                    {
                        "name": seed_name,
                        "age": str(item.get("age", "")),
                        "hints": str(item.get("hints", "")),
                        "triggerKeywords": _split_keywords(item.get("triggerKeywords", [])),
                    }
                )
        if not character_seeds:
            for existing in draft.get("characters", []):
                if isinstance(existing, dict) and str(existing.get("name", "")):
                    character_seeds.append({"name": str(existing.get("name", ""))})
        if not character_seeds:
            character_seeds = [{"name": "主角"}]

        raw_openings = outline.get("openings", [])
        normalized_openings: list[dict[str, Any]] = []
        if isinstance(raw_openings, list):
            for index, item in enumerate(raw_openings, start=1):
                if not isinstance(item, dict):
                    continue
                opening = merge_defaults(default_opening_entry(), {})
                opening["title"] = str(item.get("title", f"时间点 {index}")) or f"时间点 {index}"
                opening["greeting"] = str(item.get("greeting", ""))
                opening["scenario"] = str(item.get("scenario", ""))
                opening["exampleDialogue"] = str(item.get("exampleDialogue", ""))
                opening["firstMessage"] = str(item.get("firstMessage", ""))
                if any(
                    [
                        opening["greeting"],
                        opening["scenario"],
                        opening["exampleDialogue"],
                        opening["firstMessage"],
                    ]
                ):
                    normalized_openings.append(opening)
        if normalized_openings:
            draft["openings"] = normalized_openings
            draft["opening"] = normalized_openings[0]

        raw_locations = outline.get("locations", [])
        normalized_locations: list[dict[str, Any]] = []
        if isinstance(raw_locations, list):
            for item in raw_locations:
                if not isinstance(item, dict):
                    continue
                entry = merge_defaults(default_world_book_entry(), {})
                entry["triggerMode"] = "keyword"
                entry["title"] = str(item.get("title", ""))
                entry["keywords"] = _split_keywords(item.get("keywords", []))
                entry["content"] = str(item.get("content", ""))
                if entry["title"] and entry["content"]:
                    normalized_locations.append(entry)

        plot_openings = normalized_openings if normalized_openings else (
            draft.get("openings", []) if isinstance(draft.get("openings", []), list) else []
        )
        progression_payload: dict[str, Any] | None = outline if self._extract_plot_nodes(outline) else None
        if progression_payload is None:
            progression_prompt = build_plot_progression_prompt(
                story_text=story_text,
                story_summary=story_summary,
                characters=character_seeds,
                openings=plot_openings,
                locations=normalized_locations,
                draft=draft,
            )
            try:
                generated_progression = provider.generate(runtime_config, progression_prompt)
                parsed_progression = _extract_json_object(generated_progression)
                if isinstance(parsed_progression, dict):
                    progression_payload = parsed_progression
            except Exception:
                progression_payload = None

        plot_timeline = self._build_plot_progression_timeline(
            progression_payload=progression_payload,
            outline=outline,
            story_summary=story_summary,
            openings=plot_openings,
            locations=normalized_locations,
        )
        draft["timeline"] = plot_timeline
        combined_entries = [entry for entry in normalized_locations if str(entry.get("title", "")) != "剧情推进"]
        draft["worldBook"]["entries"] = combined_entries

        normalized_characters: list[dict[str, Any]] = []
        character_raw_outputs: list[str] = []
        for seed in character_seeds[:12]:
            character_prompt = build_character_from_story_prompt(
                target_character=seed,
                previous_characters=normalized_characters,
                story_summary=story_summary,
                story_text=story_text,
                draft=draft,
            )

            generated_character = ""
            parsed_character: dict[str, Any] = {}
            try:
                generated_character = provider.generate(runtime_config, character_prompt)
                maybe_parsed = _extract_json_object(generated_character)
                if isinstance(maybe_parsed, dict):
                    parsed_character = maybe_parsed
            except Exception:
                parsed_character = {}
            character_raw_outputs.append(generated_character)

            character = merge_defaults(default_character_entry(), {})
            character["name"] = str(parsed_character.get("name", seed.get("name", "")))
            character["age"] = str(parsed_character.get("age", seed.get("age", "")))
            keywords = _split_keywords(parsed_character.get("triggerKeywords", []))
            if not keywords:
                keywords = _split_keywords(seed.get("triggerKeywords", []))
            if not keywords and character["name"]:
                keywords = [character["name"]]
            character["triggerKeywords"] = keywords
            character["appearance"] = str(parsed_character.get("appearance", ""))
            character["personality"] = str(parsed_character.get("personality", ""))
            character["speakingStyle"] = str(parsed_character.get("speakingStyle", ""))
            character["speakingExample"] = str(parsed_character.get("speakingExample", ""))
            character["background"] = str(parsed_character.get("background", seed.get("hints", "")))
            if character["name"]:
                normalized_characters.append(character)
        if normalized_characters:
            draft["characters"] = normalized_characters

        if not draft["card"]["name"] and draft["characters"]:
            draft["card"]["name"] = draft["characters"][0]["name"]

        normalized_draft = normalize_draft(draft)
        normalized_draft["sourceType"] = "roleplaycard"
        raw_bundle = json.dumps(
            {"outline": generated_outline, "characterCalls": character_raw_outputs},
            ensure_ascii=False,
        )
        return ok({"draft": normalized_draft, "raw": raw_bundle}, "Card generated from story.")

    def generate_image_prompt(self, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_draft(draft["draft"])
        prompt, negative = build_image_prompt(normalized)
        return ok({"prompt": prompt, "negativePrompt": negative}, "Image prompt generated.")

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["imageProvider"]
        if not str(config.get("model", "")).strip():
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_image_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            image_path = provider.generate(
                config,
                payload["prompt"],
                payload.get("negativePrompt", ""),
                self.storage.cache_images_dir,
            )
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"imagePath": image_path, "prompt": payload["prompt"]}, "Image generated.")

    def resolve_image_path(self, image_path: str) -> Path:
        candidate = Path(image_path).resolve()
        base = self.storage.base_dir.resolve()
        if base not in candidate.parents and candidate != base:
            raise ValueError("Image path is outside app data directory.")
        if not candidate.exists():
            raise FileNotFoundError("Image file not found.")
        return candidate

    def upload_image_file(self, filename: str, file_bytes: bytes) -> dict[str, Any]:
        extension = Path(filename).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
            extension = ".png"
        output = self.storage.cache_images_dir / f"{uuid4()}{extension}"
        output.write_bytes(file_bytes)
        return {"path": str(output)}

    def export_character_card_download(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = normalize_draft(payload["draft"])
        export_draft = self._build_export_draft_with_timeline_entry(draft)
        image_path = str(payload.get("imagePath", "")).strip()
        card_name = export_draft["card"]["name"].strip() or export_draft["characters"][0]["name"].strip()
        primary_opening = _primary_opening(export_draft)
        if not card_name:
            return fail("Card name is required.", "validation_error")
        if not str(primary_opening.get("firstMessage", "")).strip():
            return fail("First message is required.", "validation_error")
        if not image_path:
            return fail("Image path is required.", "validation_error")

        resolved_image = self.resolve_image_path(image_path)
        prepared_path = self.storage.cache_images_dir / f"{export_draft['id']}-export.png"
        ensure_png(str(resolved_image), str(prepared_path))
        output_path = self.exports_dir / f"{uuid4()}.png"
        embed_tavern_metadata(str(prepared_path), export_draft, str(output_path))
        encoded = base64.b64encode(output_path.read_bytes()).decode("utf-8")
        filename = f"{_safe_filename(card_name)}.png"
        return ok({"filename": filename, "imageBase64": encoded}, "Character card exported.")

    def import_character_card_path(self, input_path: str) -> dict[str, Any]:
        try:
            imported = import_character_card(input_path)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "import_failed")
        source_type = str(imported.get("__importSource", "external")) if isinstance(imported, dict) else "external"
        if isinstance(imported, dict) and "__importSource" in imported:
            imported = dict(imported)
            imported.pop("__importSource", None)
        draft = normalize_draft(imported)
        draft["sourceType"] = source_type
        if not draft["card"]["name"].strip() and draft["characters"]:
            draft["card"]["name"] = draft["characters"][0]["name"]
        if Path(input_path).suffix.lower() == ".png":
            draft["illustration"]["originalImagePath"] = input_path
            draft["illustration"]["generatedImagePath"] = ""
            draft["illustration"]["exportImagePath"] = input_path
        if source_type == "external":
            draft["characters"] = [draft["characters"][0]]
        return ok({"draft": draft, "sourcePath": input_path, "sourceType": source_type}, "Character card imported.")

    def import_character_card_file(self, filename: str, file_bytes: bytes) -> dict[str, Any]:
        extension = Path(filename).suffix.lower() or ".bin"
        temp_path = self.imports_dir / f"{uuid4()}{extension}"
        temp_path.write_bytes(file_bytes)
        result = self.import_character_card_path(str(temp_path))
        if result["success"] and extension == ".png" and result["data"]:
            result["data"]["draft"]["illustration"]["originalImagePath"] = str(temp_path)
            result["data"]["draft"]["illustration"]["generatedImagePath"] = ""
            result["data"]["draft"]["illustration"]["exportImagePath"] = str(temp_path)
        return result
