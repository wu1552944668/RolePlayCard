from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service import RolePlayCardService


def test_save_and_load_draft(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "draft": {
            "card": {"name": "测试角色卡"},
            "characters": [{"name": "测试角色", "triggerKeywords": ["测试角色"]}],
        },
        "saveAs": False,
    }
    save_result = service.save_draft(payload)
    assert save_result["success"] is True

    draft_id = save_result["data"]["id"]
    load_result = service.load_draft(draft_id)
    assert load_result["success"] is True
    assert load_result["data"]["card"]["name"] == "测试角色卡"
    assert load_result["data"]["characters"][0]["name"] == "测试角色"


def test_export_character_card_embeds_tavern_metadata(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    draft = service.save_draft(
        {
            "draft": {
                "card": {"name": "露娜卡"},
                "characters": [
                    {
                        "name": "维克",
                        "isUserRole": True,
                        "appearance": "黑色风衣",
                        "personality": "沉稳克制",
                        "speakingExample": "{{user}}: 我们先去哪？\n维克: 先查码头。",
                        "background": "前特工，擅长潜入与情报分析。",
                    },
                    {
                        "name": "露娜",
                        "triggerMode": "always",
                        "appearance": "银发长外套",
                        "personality": "冷静敏锐",
                    },
                ],
                "openings": [
                    {"title": "首屏 1", "firstMessage": "你好。", "scenario": "酒馆"},
                    {"title": "首屏 2", "firstMessage": "又见面了。", "scenario": "街头"},
                ],
                "timeline": {
                    "title": "剧情推进",
                    "enabled": False,
                    "triggerMode": "always",
                    "keywords": ["剧情推进", "主线节点"],
                    "nodes": [
                        {
                            "title": "起点",
                            "timePoint": "开场",
                            "trigger": "玩家进入酒馆",
                            "event": "露娜与玩家碰面并给出任务。",
                            "objective": "建立目标",
                            "conflict": "情报不完整",
                            "outcome": "玩家接取调查线",
                            "nextHook": "前往街头",
                        }
                    ],
                },
            },
            "saveAs": False,
        }
    )["data"]

    image_path = tmp_path / "source.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(image_path, format="PNG")

    result = service.export_character_card_download({"draft": draft, "imagePath": str(image_path)})
    assert result["success"] is True
    output_path = tmp_path / "decoded.png"
    output_path.write_bytes(base64.b64decode(result["data"]["imageBase64"]))

    with Image.open(output_path) as exported:
        chara = exported.text["chara"]
        roleplaycard = exported.text["roleplaycard"]

    payload = json.loads(base64.b64decode(chara).decode("utf-8"))
    assert payload["spec"] == "chara_card_v2"
    assert payload["data"]["name"] == "露娜卡"
    assert payload["data"]["description"] == "银发长外套"
    assert payload["data"]["first_mes"] == "你好。"
    assert payload["data"]["alternate_greetings"] == ["又见面了。"]
    assert payload["data"]["character_book"]["entries"]
    user_entry = next(
        (
            entry
            for entry in payload["data"]["character_book"]["entries"]
            if isinstance(entry, dict) and entry.get("comment") == "{{user}}"
        ),
        None,
    )
    assert isinstance(user_entry, dict)
    assert user_entry.get("constant") is True
    user_content = str(user_entry.get("content", ""))
    assert "姓名: {{user}}" in user_content
    assert "背景: 前特工，擅长潜入与情报分析。" in user_content
    assert "维克:" not in user_content
    plot_book_entry = next(
        (entry for entry in payload["data"]["character_book"]["entries"] if entry.get("comment") == "剧情推进"),
        None,
    )
    assert isinstance(plot_book_entry, dict)
    structured_plot = json.loads(plot_book_entry["content"])
    assert structured_plot["guidanceType"] == "plot_progression"
    assert structured_plot["nodes"][0]["title"] == "起点"

    saved_draft = json.loads(roleplaycard)
    assert saved_draft["card"]["name"] == "露娜卡"
    assert any(entry.get("title") == "剧情推进" for entry in saved_draft["worldBook"]["entries"])


def test_import_character_card_from_exported_png(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    draft = service.save_draft(
        {
            "draft": {
                "card": {"name": "导入测试卡"},
                "characters": [{"name": "艾拉", "triggerKeywords": ["艾拉", "Ayla"]}],
                "opening": {"firstMessage": "欢迎来到测试世界。"},
                "worldBook": {
                    "entries": [
                        {
                            "title": "组织设定",
                            "keywords": ["公会"],
                            "content": "公会负责发布悬赏。",
                        }
                    ]
                },
            },
            "saveAs": False,
        }
    )["data"]

    image_path = tmp_path / "source.png"
    Image.new("RGBA", (64, 64), (0, 0, 0, 255)).save(image_path, format="PNG")
    export_result = service.export_character_card_download({"draft": draft, "imagePath": str(image_path)})
    assert export_result["success"] is True
    output_path = tmp_path / "importable.png"
    output_path.write_bytes(base64.b64decode(export_result["data"]["imageBase64"]))

    imported = service.import_character_card_path(str(output_path))
    assert imported["success"] is True
    imported_draft = imported["data"]["draft"]
    assert imported_draft["card"]["name"] == "导入测试卡"
    assert imported_draft["characters"][0]["name"] == "艾拉"
    assert imported_draft["worldBook"]["entries"]
    assert all(entry["title"] != "剧情推进" for entry in imported_draft["worldBook"]["entries"])
    assert imported_draft["timeline"]["title"] == "剧情推进"
    assert imported_draft["illustration"]["generatedImagePath"] == ""


def test_import_chara_v2_with_dict_worldbook_entries(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "测试导入卡",
            "description": "测试角色",
            "personality": "沉着冷静",
            "first_mes": "你好",
            "character_book": {
                "entries": {
                    "0": {
                        "comment": "组织设定",
                        "keys": ["组织", "联盟"],
                        "content": "这是一个跨城联盟组织。",
                        "enabled": True,
                        "constant": False,
                        "insertion_order": 210,
                    }
                }
            },
        },
    }
    input_path = tmp_path / "import-v2.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    imported = service.import_character_card_path(str(input_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "测试导入卡"
    assert draft["worldBook"]["entries"]
    entry = draft["worldBook"]["entries"][0]
    assert entry["title"] == "组织设定"
    assert "组织" in entry["keywords"]


def test_import_png_ccv3_fallback(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "CCV3卡",
            "first_mes": "你好",
            "character_book": {
                "entries": [
                    {
                        "comment": "测试条目",
                        "keys": ["关键词A"],
                        "content": "条目内容",
                    }
                ]
            },
        },
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    png_path = tmp_path / "ccv3-only.png"
    pnginfo = PngInfo()
    pnginfo.add_text("ccv3", encoded)
    Image.new("RGBA", (24, 24), (255, 255, 255, 255)).save(png_path, format="PNG", pnginfo=pnginfo)

    imported = service.import_character_card_path(str(png_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "CCV3卡"
    assert draft["worldBook"]["entries"]


def test_import_chara_v3_entries(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": "V3卡",
            "first_mes": "hello",
            "character_book": {
                "entries": [
                    {
                        "comment": "V3条目",
                        "keys": ["v3-key"],
                        "content": "v3 content",
                        "enabled": True,
                        "constant": False,
                        "position": "after_char",
                    }
                ]
            },
        },
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    png_path = tmp_path / "v3.png"
    pnginfo = PngInfo()
    pnginfo.add_text("chara", encoded)
    Image.new("RGBA", (20, 20), (0, 0, 0, 255)).save(png_path, format="PNG", pnginfo=pnginfo)

    imported = service.import_character_card_path(str(png_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "V3卡"
    assert len(draft["worldBook"]["entries"]) == 1


def test_import_chara_alternate_greetings_to_openings(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "多首屏测试",
            "scenario": "图书馆",
            "first_mes": "这是主首屏",
            "alternate_greetings": ["这是候选首屏A", "这是候选首屏B"],
        },
    }
    input_path = tmp_path / "multi-openings.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    imported = service.import_character_card_path(str(input_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert len(draft["openings"]) == 3
    assert draft["openings"][0]["firstMessage"] == "这是主首屏"
    assert draft["openings"][1]["firstMessage"] == "这是候选首屏A"
    assert draft["openings"][2]["firstMessage"] == "这是候选首屏B"


def test_clear_all_data(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    service.save_draft({"draft": {"card": {"name": "待删除草稿"}}, "saveAs": False})
    service.upload_image_file("temp.png", b"123")
    (tmp_path / "imports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports" / "file.bin").write_bytes(b"abc")
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "exports" / "file.bin").write_bytes(b"abc")

    cleared = service.clear_all_data()
    assert cleared["success"] is True
    assert service.list_drafts()["data"] == []
    assert (tmp_path / "drafts").exists()
    assert (tmp_path / "cache" / "images").exists()
    assert (tmp_path / "imports").exists()
    assert (tmp_path / "exports").exists()


def test_generate_card_from_story_multiple_characters_and_locations(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0
            self.prompts = []

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            self.prompts.append(prompt)
            if self.calls == 1:
                assert "不同重要时间点/阶段" in prompt
                assert "plotProgression" in prompt
                return json.dumps(
                    {
                        "storySummary": "两位主角共同调查旧案，主要活动地点是仓库与档案馆。",
                        "card": {"name": "长篇小说角色卡", "description": "多角色叙事"},
                        "characters": [
                            {"name": "林夏", "age": "22", "hints": "记者，行动快，擅长追线索"},
                            {"name": "顾沉", "age": "27", "hints": "刑警，稳重理性，重证据"},
                        ],
                        "openings": [
                            {
                                "title": "雨夜调查",
                                "greeting": "我们又见面了。",
                                "scenario": "暴雨中的旧城区",
                                "exampleDialogue": "林夏：线索在仓库。\n顾沉：我先探路。",
                                "firstMessage": "雨声盖过脚步声，你在路灯下看到我向你招手。",
                            }
                        ],
                        "locations": [
                            {
                                "title": "旧城区仓库",
                                "keywords": ["仓库", "旧城区"],
                                "content": "废弃仓库，夜晚常有可疑交易。",
                            },
                            {
                                "title": "中央档案馆",
                                "keywords": ["档案馆", "资料"],
                                "content": "保存城市历史案件卷宗，权限严格。",
                            },
                        ],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "title": "雨夜接触",
                                    "timePoint": "开端",
                                    "trigger": "玩家抵达旧城区",
                                    "event": "林夏与顾沉向玩家说明旧案异动。",
                                    "objective": "建立合作并确定调查方向",
                                    "conflict": "双方对线索来源不完全信任",
                                    "outcome": "决定先查仓库再查档案馆",
                                    "nextHook": "仓库交易记录",
                                },
                                {
                                    "title": "仓库对峙",
                                    "timePoint": "中段",
                                    "trigger": "发现匿名交易痕迹",
                                    "event": "三人确认旧案与走私链条有关。",
                                    "objective": "锁定幕后组织",
                                    "conflict": "线索被人为清理",
                                    "outcome": "转向档案馆核验旧卷宗",
                                    "nextHook": "档案权限异常",
                                },
                                {
                                    "title": "档案揭示",
                                    "timePoint": "后段",
                                    "trigger": "取得核心卷宗",
                                    "event": "核心证据显示旧案被系统性篡改。",
                                    "objective": "形成下一阶段抓捕策略",
                                    "conflict": "对手提前察觉并反制",
                                    "outcome": "主线进入公开对抗阶段",
                                    "nextHook": "寻找内部协助者",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                assert "已生成角色（监督输入，必须参考）" in prompt
                assert "[]" in prompt
                assert "这里是一段包含两位主角和两个主要地点的小说内容。" in prompt
                return json.dumps(
                    {
                        "name": "林夏",
                        "age": "22",
                        "triggerKeywords": ["林夏", "记者", "调查"],
                        "appearance": "黑发，短外套",
                        "personality": "冷静执着",
                        "speakingStyle": "简洁直接",
                        "speakingExample": "{{user}}: 先去哪？\n林夏: 先去仓库，线索不会等人。",
                        "background": "城市调查记者",
                    },
                    ensure_ascii=False,
                )
            if self.calls == 3:
                assert "林夏" in prompt
                assert "这里是一段包含两位主角和两个主要地点的小说内容。" in prompt
                return json.dumps(
                    {
                        "name": "顾沉",
                        "age": "27",
                        "triggerKeywords": ["顾沉", "刑警", "证据"],
                        "appearance": "高个，风衣",
                        "personality": "克制理性",
                        "speakingStyle": "平稳低声",
                        "speakingExample": "{{user}}: 现在抓人吗？\n顾沉: 不，证据链先补齐。",
                        "background": "重案组刑警",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "这里是一段包含两位主角和两个主要地点的小说内容。",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert draft["card"]["name"] == "长篇小说角色卡"
    assert len(draft["characters"]) == 2
    assert draft["characters"][0]["name"] == "林夏"
    assert draft["characters"][0]["age"] == "22"
    assert draft["characters"][1]["name"] == "顾沉"
    assert len(draft["worldBook"]["entries"]) == 2
    assert all(entry["triggerMode"] == "keyword" for entry in draft["worldBook"]["entries"])
    assert all(entry["title"] != "剧情推进" for entry in draft["worldBook"]["entries"])
    assert draft["timeline"]["title"] == "剧情推进"
    assert draft["timeline"]["triggerMode"] == "always"
    assert draft["timeline"]["enabled"] is False
    assert len(draft["timeline"]["nodes"]) >= 3
    assert draft["timeline"]["nodes"][0]["parentId"] == ""
    assert draft["timeline"]["nodes"][1]["parentId"] == draft["timeline"]["nodes"][0]["id"]
    assert draft["timeline"]["nodes"][2]["parentId"] == draft["timeline"]["nodes"][1]["id"]
    assert dummy_provider.calls == 3


def test_generate_card_from_story_fallback_plot_progression_when_missing(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "storySummary": "一位调查员追查港口失踪案。",
                        "card": {"name": "失踪案追查", "description": "单角色测试"},
                        "characters": [{"name": "阿澈", "age": "24", "hints": "调查员"}],
                        "openings": [
                            {
                                "title": "深夜港口",
                                "greeting": "你来晚了。",
                                "scenario": "暴雨夜的港口仓区",
                                "exampleDialogue": "阿澈：线索在码头。\n你：有人跟踪你吗？",
                                "firstMessage": "你刚靠近堆场，我从暗处把你拽进雨棚。",
                            }
                        ],
                        "locations": [
                            {
                                "title": "北码头仓区",
                                "keywords": ["码头", "仓区"],
                                "content": "夜间货运频繁，监控盲区较多。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                assert "剧情推进结构化指导生成器" in prompt
                # 第二次调用：剧情推进结构化指导，故意返回非 JSON 触发 fallback。
                return "not-json"
            if self.calls == 3:
                return json.dumps(
                    {
                        "name": "阿澈",
                        "age": "24",
                        "triggerKeywords": ["阿澈", "调查员"],
                        "appearance": "黑色雨衣，短发",
                        "personality": "谨慎敏锐",
                        "speakingStyle": "低声简短",
                        "speakingExample": "{{user}}: 现在怎么办？\n阿澈: 先看货单，再看人。",
                        "background": "长期追查港口案件",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "短篇小说文本",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert len(draft["worldBook"]["entries"]) == 1
    assert all(entry["title"] != "剧情推进" for entry in draft["worldBook"]["entries"])
    assert draft["timeline"]["triggerMode"] == "always"
    assert draft["timeline"]["enabled"] is False
    assert len(draft["timeline"]["nodes"]) >= 3
    assert draft["timeline"]["nodes"][0]["parentId"] == ""
    assert draft["timeline"]["nodes"][1]["parentId"] == draft["timeline"]["nodes"][0]["id"]
    assert draft["timeline"]["nodes"][2]["parentId"] == draft["timeline"]["nodes"][1]["id"]
    assert dummy_provider.calls == 3


def test_generate_card_from_story_branches_when_same_timepoint(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "storySummary": "分叉测试",
                        "card": {"name": "分叉结构测试", "description": "时间线分叉"},
                        "characters": [{"name": "伊芙", "age": "21", "hints": "调查员"}],
                        "openings": [
                            {
                                "title": "开场",
                                "greeting": "开始吧。",
                                "scenario": "雨夜街区",
                                "exampleDialogue": "伊芙：我们分头查。",
                                "firstMessage": "雨夜里你看见我在路口挥手。",
                            }
                        ],
                        "locations": [{"title": "街区", "keywords": ["街区"], "content": "案发现场附近。"}],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "title": "节点A",
                                    "timePoint": "开端",
                                    "trigger": "玩家到场",
                                    "event": "接到主线",
                                    "objective": "建立目标",
                                    "conflict": "线索不足",
                                    "outcome": "进入调查",
                                    "nextHook": "中段A",
                                },
                                {
                                    "title": "节点B1",
                                    "timePoint": "中段",
                                    "trigger": "查第一条线",
                                    "event": "锁定嫌疑人甲",
                                    "objective": "确认动机",
                                    "conflict": "证词矛盾",
                                    "outcome": "出现分支1",
                                    "nextHook": "后段",
                                },
                                {
                                    "title": "节点B2",
                                    "timePoint": "中段",
                                    "trigger": "查第二条线",
                                    "event": "锁定嫌疑人乙",
                                    "objective": "确认不在场证明",
                                    "conflict": "监控缺失",
                                    "outcome": "出现分支2",
                                    "nextHook": "后段",
                                },
                                {
                                    "title": "节点C",
                                    "timePoint": "后段",
                                    "trigger": "合并两条线索",
                                    "event": "逼近真相",
                                    "objective": "收束主线",
                                    "conflict": "对手反制",
                                    "outcome": "终局前夜",
                                    "nextHook": "终局",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                return json.dumps(
                    {
                        "name": "伊芙",
                        "age": "21",
                        "triggerKeywords": ["伊芙", "调查员"],
                        "appearance": "短发，风衣",
                        "personality": "冷静",
                        "speakingStyle": "简练",
                        "speakingExample": "{{user}}: 接下来？\n伊芙: 两条线并查。",
                        "background": "调查员",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "分叉小说文本",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    nodes = result["data"]["draft"]["timeline"]["nodes"]
    assert len(nodes) >= 4

    node_a = nodes[0]
    node_b1 = nodes[1]
    node_b2 = nodes[2]
    node_c = nodes[3]

    assert node_a["parentId"] == ""
    assert node_b1["parentId"] == node_a["id"]
    assert node_b2["parentId"] == node_a["id"]
    assert node_c["parentId"] == node_b1["id"]
    assert dummy_provider.calls == 2


def test_plot_progression_worldbook_entry_migrates_to_timeline(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "draft": {
            "card": {"name": "迁移测试卡"},
            "worldBook": {
                "entries": [
                    {
                        "title": "剧情推进",
                        "triggerMode": "always",
                        "enabled": False,
                        "keywords": ["剧情推进", "主线节点"],
                        "content": json.dumps(
                            {
                                "guidanceType": "plot_progression",
                                "nodes": [
                                    {
                                        "title": "节点A",
                                        "timePoint": "开端",
                                        "trigger": "遇见关键角色",
                                        "event": "开始调查",
                                        "objective": "确定目标",
                                        "conflict": "信息不足",
                                        "outcome": "进入下一阶段",
                                        "nextHook": "前往仓库",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "title": "普通地点",
                        "keywords": ["仓库"],
                        "content": "一处普通地点。",
                    },
                ]
            },
        },
        "saveAs": False,
    }
    saved = service.save_draft(payload)
    assert saved["success"] is True
    normalized = saved["data"]
    assert normalized["timeline"]["title"] == "剧情推进"
    assert len(normalized["timeline"]["nodes"]) == 1
    assert normalized["timeline"]["nodes"][0]["title"] == "节点A"
    assert all(entry["title"] != "剧情推进" for entry in normalized["worldBook"]["entries"])
    assert len(normalized["worldBook"]["entries"]) == 1


def test_list_text_prefix_prompts(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "gpt-4o.txt").write_text("内置破限 A", encoding="utf-8")
    (prompts_dir / "gpt-4.1.txt").write_text("内置破限 B", encoding="utf-8")
    service.text_prefix_prompts_dir = prompts_dir

    result = service.list_text_prefix_prompts()
    assert result["success"] is True
    assert result["data"]["directory"] == str(prompts_dir)
    assert result["data"]["items"] == [
        {"model": "gpt-4.1", "filename": "gpt-4.1.txt"},
        {"model": "gpt-4o", "filename": "gpt-4o.txt"},
    ]


def test_generate_field_uses_builtin_prefix_prompt(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "gpt-4o.txt").write_text("这是内置前置词", encoding="utf-8")
    service.text_prefix_prompts_dir = prompts_dir

    class DummyTextProvider:
        def __init__(self):
            self.last_config = {}

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.last_config = dict(config)
            return "生成结果"

        def list_models(self, config):
            return ["gpt-4o"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "field": "card.description",
        "mode": "generate",
        "userInput": "",
        "draft": {"card": {"name": "测试卡", "description": ""}},
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "gpt-4o",
                "prefixPromptMode": "builtin",
                "builtinPrefixPromptModel": "gpt-4o",
                "prefixPrompt": "这是自定义兜底词",
            }
        },
    }
    result = service.generate_field(payload)
    assert result["success"] is True
    assert dummy_provider.last_config["prefixPrompt"] == "这是内置前置词"


def test_generate_field_builtin_prefix_fallbacks_to_custom_when_missing(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    service.text_prefix_prompts_dir = prompts_dir

    class DummyTextProvider:
        def __init__(self):
            self.last_config = {}

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.last_config = dict(config)
            return "生成结果"

        def list_models(self, config):
            return ["gpt-4o"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "field": "card.description",
        "mode": "generate",
        "userInput": "",
        "draft": {"card": {"name": "测试卡", "description": ""}},
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "gpt-4o",
                "prefixPromptMode": "builtin",
                "builtinPrefixPromptModel": "gpt-4o",
                "prefixPrompt": "这是自定义兜底词",
            }
        },
    }
    result = service.generate_field(payload)
    assert result["success"] is True
    assert dummy_provider.last_config["prefixPrompt"] == "这是自定义兜底词"
