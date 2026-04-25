from __future__ import annotations

import json
import re
from textwrap import dedent


FIELD_GUIDANCE = {
    "card.name": "给角色卡起一个简洁、好记、可概括整体设定的名称。",
    "card.description": "概括角色卡主题、世界背景和玩法导向，控制在 2-5 句。",
    "characters.*.name": "给该角色起一个符合设定且有辨识度的名字。",
    "characters.*.triggerKeywords": "给出用于触发该角色世界书条目的关键词，使用逗号分隔。",
    "characters.*.age": "输出符合设定的年龄或外观年龄，简洁直接。",
    "characters.*.appearance": "描述外貌，突出发型、服饰、体态和辨识特征。",
    "characters.*.personality": "概括性格特征、核心动机和行为倾向。",
    "characters.*.speakingStyle": "描述该角色的说话方式、语气和词汇习惯。",
    "characters.*.speakingExample": "写成对话体示例，至少 2 轮，用 `{{user}}:` 与 `角色名:` 的格式。",
    "characters.*.background": "概述成长经历、身份设定与关键事件。",
    "opening.greeting": "写一句简洁的角色卡开场问候。",
    "opening.scenario": "概括当前场景，给出时间、地点和氛围。",
    "opening.exampleDialogue": "提供一段体现角色卡整体风格的示例对话。",
    "opening.firstMessage": "写成可直接用于 TavernAI 的首条消息。",
    "openings.*.greeting": "写一句简洁的角色卡开场问候。",
    "openings.*.scenario": "概括当前场景，给出时间、地点和氛围。",
    "openings.*.exampleDialogue": "提供一段体现角色卡整体风格的示例对话。",
    "openings.*.firstMessage": "写成可直接用于 TavernAI 的首条消息。",
    "worldBook.entries.*.title": "写一个方便检索的世界书条目标题。",
    "worldBook.entries.*.keywords": "给出触发关键词，使用逗号分隔。",
    "worldBook.entries.*.content": "写成独立可读的设定条目内容，避免依赖上下文代词。",
}

FIELD_EXAMPLES = {
    "card.name": [
        "雾港旧案档案室",
        "北岸异常调查组",
    ],
    "card.description": [
        "近未来港口都市的群像调查角色卡，强调悬疑线索与角色关系推进。",
        "玩家将与多名关键人物协作破案，主打冷色都市氛围与慢节奏推理。",
    ],
    "characters.*.name": [
        "洛菈",
        "尤兰达·雷文",
    ],
    "characters.*.triggerKeywords": [
        "洛菈，小洛",
        "尤兰达，雷文",
    ],
    "characters.*.age": [
        "22",
        "30",
    ],
    "characters.*.appearance": [
        '''基础特征:
                - 银白长发，束成高马尾
                - 皮肤白皙，触感柔软
                - 站姿笔挺，手持银白重型长枪
            面部细节:
                - 浅蓝色双眸，目光锐利直白
                - 鼻梁高挺
                - 嘴唇略薄，不苟言笑时呈平直线
                - 战斗时眉头微微压低，瞳孔紧缩
            身材体征:
                - 高挑匀称，腰肢纤细，无明显大块肌肉痕迹
                - 臀部: 曲线圆润饱满，臀肉柔软有弹性。
                - 双腿: 修长，大腿肉感丰盈，小腿线条流畅紧绷。''',
        '''基础特征:
                - 暗红色齐脖短发，发顶有两只隐蔽的同色猫耳
                - 小麦色皮肤
                - 瞳孔呈竖瞳状的金琥珀色，眼尾天然上挑的猫眼
            面部细节:
                - 右侧眉骨有一道斜向断眉
                - 笑起来时会露出两颗尖锐的小虎牙
                - 嘴唇丰润，常涂暗红色唇脂
                - 锁定猎物或进入战斗状态时，会习惯性地舔舐上唇
            身材体征:
                - 骨架纤细，身形柔韧，四肢修长且充满爆发力
                - 胸部饱满沉甸，走动时有明显晃动感
                - 腹部有清晰的马甲线，腰肢纤细盈握
                - 臀部圆润上翘，身后有一条暗红色细长猫尾''',
    ],
    "characters.*.personality": [
        "冷静克制，习惯先观察后行动，对真相有执念。",
        "外冷内热，重承诺，面对危险时决断迅速。",
    ],
    "characters.*.speakingStyle": [
        "句子短，信息密度高，少用情绪词。",
        "语气平稳但压迫感强，常以反问推进对话。",
    ],
    "characters.*.speakingExample": [
        "{{user}}: 你好，你看起来很赶。\n林夏: 嗯，案发现场刚有新线索。先跟我走，路上我讲细节。",
        "{{user}}: 你为什么一直盯着那份记录？\n顾沉: 因为它被改过三次。你先回答我，你昨晚几点到的仓库？",
    ],
    "characters.*.background": [
        "曾任都市媒体记者，因追查旧案离职，现以自由身份调查。",
        "重案组出身，处理过多起失踪案，对档案系统异常敏感。",
    ],
    "opening.greeting": [
        "晚上好，你也在查这起案子？",
        "别紧张，我只是来确认你是否站在同一边。",
    ],
    "opening.scenario": [
        "深夜港区仓库，雨声很大，路灯忽明忽暗。",
        "档案馆地下层，旧风机轰鸣，纸页有霉味。",
    ],
    "opening.exampleDialogue": [
        "林夏：这份记录被改过。\n顾沉：改过不止一次，手法还不同。",
        "你：为什么叫我来？\n她：因为你是最后见过受害者的人。",
    ],
    "opening.firstMessage": [
        "雨夜里你推开生锈铁门，我正站在堆满旧木箱的走道尽头，示意你别出声。",
        "档案灯管闪了两下，你听见身后脚步靠近，我把一份泛黄卷宗塞进你手里。",
    ],
    "openings.*.greeting": [
        "终于等到你了，我们得马上开始。",
        "你来得正好，这里有你必须看的东西。",
    ],
    "openings.*.scenario": [
        "凌晨地铁终点站，站台几乎空无一人。",
        "废弃电台天台，冷风夹着潮湿雾气。",
    ],
    "openings.*.exampleDialogue": [
        "你：我们还要信任他吗？\n她：信任不重要，结果才重要。",
        "他：你听见了吗？\n你：听见了，不止一个人。",
    ],
    "openings.*.firstMessage": [
        "电台塔顶红灯一闪一闪，你刚踏上最后一级台阶，就看见我把对讲机递了过来。",
        "列车进站风压掀起你的衣角，我从广告灯箱后走出，低声喊了你的名字。",
    ],
    "worldBook.entries.*.title": [
        "旧城区仓库群",
        "南部丰原-精灵王庭",
    ],
    "worldBook.entries.*.keywords": [
        "仓库, 旧城区, 走私",
        "精灵王庭, 翡翠叶海, 纯血精灵",
    ],
    "worldBook.entries.*.content": [
        "旧城区仓库群长期闲置，夜间常出现匿名车辆，部分仓库地下有改造痕迹。",
        "盘踞在丰原腹地的原始森林中心，被参天古木的巨大穹顶包裹。内部由资深高阶术骑与奶骑组成的纯白元老院统领，外围由翡翠禁卫负责守卫。",
    ],
}


def _trim(text: str, limit: int | None = 900) -> str:
    _ = limit
    return str(text or "")


def _normalize_field(field: str) -> str:
    return re.sub(r"\.\d+\.", ".*.", f"{field}.").rstrip(".")


def _render_character_context(characters: list[dict]) -> str:
    lines: list[str] = []
    for idx, character in enumerate(characters[:6], start=1):
        lines.extend(
            [
                f"角色{idx} 名称: {_trim(character.get('name', ''), 80)}",
                f"角色{idx} 关键词: {', '.join(character.get('triggerKeywords', []))}",
                f"角色{idx} 外貌: {_trim(character.get('appearance', ''), 180)}",
                f"角色{idx} 性格: {_trim(character.get('personality', ''), 180)}",
                f"角色{idx} 背景: {_trim(character.get('background', ''), 180)}",
            ]
        )
    return "\n".join(line for line in lines if not line.endswith(": "))


def _render_world_book_context(entries: list[dict]) -> str:
    lines: list[str] = []
    for idx, entry in enumerate(entries[:8], start=1):
        lines.extend(
            [
                f"条目{idx} 标题: {_trim(entry.get('title', ''), 80)}",
                f"条目{idx} 触发模式: {'蓝灯常驻' if entry.get('triggerMode') == 'always' else '绿灯关键词'}",
                f"条目{idx} 关键词: {', '.join(entry.get('keywords', []))}",
                f"条目{idx} 内容: {_trim(entry.get('content', ''), 180)}",
            ]
        )
    return "\n".join(line for line in lines if not line.endswith(": "))


def build_context(draft: dict) -> str:
    card = draft.get("card", {})
    openings = draft.get("openings", [])
    if not isinstance(openings, list):
        openings = []
    primary_opening = openings[0] if openings and isinstance(openings[0], dict) else draft.get("opening", {})
    characters = draft.get("characters", [])
    world_entries = draft.get("worldBook", {}).get("entries", [])
    parts = [
        f"角色卡名称: {_trim(card.get('name', ''), 120)}",
        f"角色卡描述: {_trim(card.get('description', ''), 320)}",
        f"首屏信息数量: {len(openings) if openings else 1}",
        f"开场白: {_trim(primary_opening.get('greeting', ''), 220)}",
        f"场景: {_trim(primary_opening.get('scenario', ''), 280)}",
        f"首条消息: {_trim(primary_opening.get('firstMessage', ''), 360)}",
        f"角色数量: {len(characters)}",
        _render_character_context(characters),
        f"世界书条目数量: {len(world_entries)}",
        _render_world_book_context(world_entries),
    ]
    return "\n".join(part for part in parts if part and not part.endswith(": "))


def build_field_prompt(field: str, mode: str, user_input: str, draft: dict) -> str:
    normalized = _normalize_field(field)
    instruction = FIELD_GUIDANCE.get(normalized, "根据已知设定生成当前字段内容。")
    examples = FIELD_EXAMPLES.get(normalized, [])
    example_block = "\n".join(f"- {item}" for item in examples) if examples else "- （无示例）"
    action = "改写并增强" if mode == "rewrite" else "生成"
    extra_requirements: list[str] = []
    if normalized == "characters.*.speakingExample":
        extra_requirements.append("4. speakingExample 必须使用对话体，按 `{{user}}:` 与角色名开头逐行书写。")
    if normalized == "characters.*.triggerKeywords":
        extra_requirements.append(f"4. {_build_trigger_keywords_contract()}")
    if normalized == "characters.*.appearance":
        extra_requirements.append(
            "4. "
            + _build_appearance_contract().replace("\n", "\n   ")
        )
    extra_requirement_text = "\n".join(extra_requirements)
    return dedent(
        f"""
        你正在协助创建 AI 角色卡（多角色 + 世界书条目模式）。
        任务: {action} 字段 {field}
        要求: {instruction}

        当前字段已有内容:
        {_trim(user_input, None) or '无'}

        字段示例（可参考风格，不要机械照抄）:
        {example_block}

        已填写上下文:
        {build_context(draft)}

        输出要求:
        1. 只输出字段正文，不要加标题和解释。
        2. 保持设定一致，避免与已有角色和世界书冲突。
        3. 优先生成可直接粘贴到角色卡中的自然中文。
        {extra_requirement_text}
        """
    )


def build_image_prompt(draft: dict) -> tuple[str, str]:
    card = draft.get("card", {})
    characters = draft.get("characters", [])
    primary = characters[0] if characters else {}
    style = _trim(draft.get("illustration", {}).get("stylePrompt", ""), 200)
    prompt = dedent(
        f"""
        Character card illustration, high detail, clean composition.
        Card name: {_trim(card.get('name', ''), 80)}
        Card concept: {_trim(card.get('description', ''), 220)}
        Focus character: {_trim(primary.get('name', ''), 80)}
        Age: {_trim(primary.get('age', ''), 60)}
        Appearance: {_trim(primary.get('appearance', ''), 260)}
        Personality vibe: {_trim(primary.get('personality', ''), 220)}
        Background cues: {_trim(primary.get('background', ''), 220)}
        Style preference: {style or 'cinematic anime portrait, expressive lighting, polished illustration'}
        """
    ).replace("\n", " ")
    negative = "low quality, blurry, extra fingers, text, watermark, cropped face, distorted anatomy"
    return prompt, negative


def _json_preview(value: object, limit: int | None = 2400) -> str:
    return _trim(json.dumps(value, ensure_ascii=False), limit)


def _extract_section_titles(text: str) -> list[str]:
    titles: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("-"):
            continue
        matched = re.fullmatch(r"([^:：]{1,24})[:：]", line)
        if not matched:
            continue
        title = matched.group(1).strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def _appearance_section_titles() -> list[str]:
    titles: list[str] = []
    for item in FIELD_EXAMPLES.get("characters.*.appearance", []):
        for title in _extract_section_titles(str(item)):
            if title not in titles:
                titles.append(title)
    return titles or ["基础特征", "面部细节", "身材体征"]


def _build_trigger_keywords_contract() -> str:
    return "triggerKeywords 必须贴近示例写法：优先使用角色名、简称、别称、常用称呼，避免“男主/女主/她/他”等泛词；建议 2-6 个关键词。"


def _build_appearance_contract() -> str:
    section_titles = _appearance_section_titles()
    section_order = " -> ".join(f"{title}:" for title in section_titles)
    lines = [
        f"appearance 必须使用多行分段格式，分段顺序为：{section_order}",
        "每个分段必须单独占一行标题，并且至少 2 条以 `- ` 开头的要点。",
        "appearance 不允许只写成一段散文或一句话。",
    ]
    return "\n".join(lines)


def _render_character_generation_examples() -> str:
    example_fields = [
        ("name", "characters.*.name"),
        ("triggerKeywords", "characters.*.triggerKeywords"),
        ("appearance", "characters.*.appearance"),
        ("personality", "characters.*.personality"),
        ("speakingStyle", "characters.*.speakingStyle"),
        ("speakingExample", "characters.*.speakingExample"),
        ("background", "characters.*.background"),
    ]
    lines: list[str] = []
    for label, key in example_fields:
        examples = FIELD_EXAMPLES.get(key, [])
        if not examples:
            continue
        lines.append(f"- {label}:")
        lines.extend([f"  - {_trim(str(item), 260)}" for item in examples[:2]])
    return "\n".join(lines) if lines else "- （无示例）"


def build_story_outline_prompt(story_text: str, draft: dict) -> str:
    return dedent(
        f"""
        你是角色卡结构提取器。请从“短篇小说/剧情文本”中抽取主干信息，并返回严格 JSON。
        要求：
        1. 必须识别多个主要角色（若存在），角色只输出“种子信息”，不要展开长篇细节。
        2. 必须识别多个主要地点（若存在），并产出世界书条目草稿。
        3. openings 需要对应故事中的“不同重要时间点/阶段”，按时间推进顺序给出多个首屏（若文本存在多个关键节点）。
        4. 必须给出剧情推进结构 plotProgression，用节点化方式拆解主线走向。
        5. 需要给出 storySummary，供后续逐角色生成使用。
        6. 输出必须是合法 JSON，不要加 markdown，不要解释。

        输出 JSON 结构：
        {{
          "storySummary": "80-200字摘要，概括主线、冲突、关系与主要地点",
          "card": {{
            "name": "角色卡名称",
            "description": "角色卡描述"
          }},
          "characters": [
            {{
              "name": "角色名",
              "age": "年龄或外观年龄",
              "hints": "该角色的关键线索，60-120字"
            }}
          ],
          "openings": [
            {{
              "title": "时间点标题（如：雨夜初遇 / 档案馆对峙）",
              "greeting": "开场白",
              "scenario": "该时间点的场景（包含时间/地点/局势）",
              "exampleDialogue": "示例对话",
              "firstMessage": "首条消息"
            }}
          ],
          "locations": [
            {{
              "title": "地点名",
              "keywords": ["地点关键词1", "地点关键词2"],
              "content": "地点信息"
            }}
          ],
          "plotProgression": {{
            "nodes": [
              {{
                "id": "节点ID（如 n1）",
                "title": "节点标题",
                "parentId": "父节点ID，根节点填空字符串",
                "timePoint": "时间点/阶段",
                "trigger": "触发条件",
                "event": "关键事件",
                "objective": "角色目标",
                "conflict": "主要冲突或阻碍",
                "outcome": "节点结果",
                "nextHook": "下一节点衔接线索"
              }}
            ]
          }}
        }}

        额外约束：
        1. openings 优先给 2-5 个关键时间点，不要只给一个静态场景。
        2. plotProgression.nodes 至少 3 个，按剧情推进顺序排列，避免空洞描述。
        3. 所有字段内容应可直接用于角色卡编辑，不写“待补充”“略”等占位词。
        4. plotProgression 支持树结构：主线节点 parentId 为空，分支节点指向父节点 id。
        5. 每个 plotProgression 节点必须包含稳定 id，且同一输出中 id 不可重复。
        6. 时间最前的第一个节点必须是根节点（parentId 为空）；时间继续向后时，默认是前一节点的子节点。
        7. 若同一时间点出现多个并行发展节点，则它们都应挂在同一父节点下形成分叉。
        8. 若出现明显时间断层（如“三年前/童年回忆”后切回“当前/今夜/次日”），新阶段节点必须另起根节点（parentId 为空），不要强行续接。
        9. 节点字段需简洁：title/timePoint 不超过 20 字；trigger/objective/conflict/outcome/nextHook 不超过 40 字；event 不超过 80 字。

        注意：
        - locations 与 plotProgression 是不同维度：locations 写“地点设定”，plotProgression 写“剧情节点推进”。
        - 不要输出 JSON 之外的任何文字。

        已有草稿上下文（可参考但不受限）：
        {build_context(draft)}

        小说文本：
        {_trim(story_text, None)}
        """
    )


def build_story_outline_prompt_segment(story_text: str, draft: dict) -> str:
    return dedent(
        f"""
        你是角色卡结构提取器。当前任务是“长篇分段增量提取”，必须返回严格 JSON。

        关键要求：
        1. 只抽取当前分段文本中出现/明确提及的信息，不要臆造分段外剧情。
        2. 输出尽量精炼，避免长段落；保证 JSON 完整闭合。
        3. 不要 markdown，不要解释，不要额外文字。

        输出 JSON 结构：
        {{
          "storySummary": "40-120字，仅总结本段",
          "card": {{
            "name": "可为空字符串",
            "description": "可为空字符串"
          }},
          "characters": [
            {{
              "name": "角色名",
              "age": "可为空",
              "hints": "30-80字",
              "triggerKeywords": ["关键词1", "关键词2"]
            }}
          ],
          "openings": [
            {{
              "title": "时间点标题",
              "greeting": "可为空",
              "scenario": "场景摘要",
              "exampleDialogue": "可为空",
              "firstMessage": "首条消息"
            }}
          ],
          "locations": [
            {{
              "title": "地点名",
              "keywords": ["关键词1", "关键词2"],
              "content": "地点摘要"
            }}
          ],
          "plotProgression": {{
            "nodes": [
              {{
                "id": "n1",
                "title": "节点标题",
                "parentId": "",
                "timePoint": "时间点",
                "trigger": "触发条件",
                "event": "关键事件",
                "objective": "目标",
                "conflict": "冲突",
                "outcome": "结果",
                "nextHook": "后续线索"
              }}
            ]
          }}
        }}

        数量上限（务必遵守）：
        - characters 最多 4 个
        - openings 最多 3 个
        - locations 最多 5 个
        - plotProgression.nodes 最多 6 个，最少 2 个
        - 节点字段简洁：title/timePoint <= 20 字；trigger/objective/conflict/outcome/nextHook <= 36 字；event <= 72 字
        - 若“回忆/三年前”切换到“当前/今夜/次日”等主线阶段，必须另起根节点（parentId 为空）

        已有草稿上下文（可参考但不受限）：
        {build_context(draft)}

        当前分段文本：
        {_trim(story_text, None)}
        """
    )


def build_character_from_story_prompt(
    target_character: dict,
    previous_characters: list[dict],
    story_summary: str,
    story_text: str,
    draft: dict,
) -> str:
    target_name = _trim(str(target_character.get("name", "")), 120)
    example_block = _render_character_generation_examples()
    trigger_keywords_contract = _build_trigger_keywords_contract()
    appearance_contract = _build_appearance_contract()
    return dedent(
        f"""
        你是角色卡生成器。请只为“一个目标角色”生成完整字段，并返回严格 JSON 对象。
        目标角色：{target_name or '未命名角色'}

        生成要求：
        1. 字段完整：name, age, triggerKeywords, appearance, personality, speakingStyle, speakingExample, background。
        2. speakingExample 必须是对话体，至少 2 轮，使用 `{{{{user}}}}:` 与 `角色名:` 逐行书写。
        3. 必须与“已生成角色”保持一致，不冲突，并避免重复设定。
        4. {trigger_keywords_contract}
        5. {appearance_contract}
        6. 输出必须是合法 JSON 对象，不要 markdown，不要解释。

        字段示例（形式为硬约束，内容按故事改写）：
        {example_block}

        输出 JSON 结构：
        {{
          "name": "角色名",
          "age": "年龄或外观年龄",
          "triggerKeywords": ["关键词1", "关键词2"],
          "appearance": "外貌",
          "personality": "性格",
          "speakingStyle": "说话方式",
          "speakingExample": "{{{{user}}}}: ...\\n角色名: ...",
          "background": "背景"
        }}

        目标角色种子信息：
        {_json_preview(target_character, 1200)}

        已生成角色（监督输入，必须参考）：
        {_json_preview(previous_characters, 2400) if previous_characters else "[]"}

        故事摘要：
        {_trim(story_summary, None) or "无"}

        故事原文全文（必须参考，不可忽略）：
        {_trim(story_text, None) or "无"}

        当前草稿上下文：
        {build_context(draft)}

        输出前自检（不要输出本段）：
        1. triggerKeywords 是否符合示例表达方式（名词化称呼、非泛词）。
        2. appearance 是否是分段 + 要点格式，而不是散文段落。
        """
    )


def build_plot_progression_prompt(
    story_text: str,
    story_summary: str,
    characters: list[dict],
    openings: list[dict],
    locations: list[dict],
    draft: dict,
) -> str:
    return dedent(
        f"""
        你是剧情推进结构化指导生成器。请基于“故事原文全文”输出严格 JSON，对主线推进进行节点化拆解。
        输出必须是合法 JSON，不要 markdown，不要解释。

        输出 JSON 结构：
        {{
          "plotProgression": {{
            "nodes": [
              {{
                "id": "节点ID（如 n1）",
                "title": "节点标题",
                "parentId": "父节点ID，根节点填空字符串",
                "timePoint": "时间点/阶段",
                "trigger": "触发条件",
                "event": "关键事件",
                "objective": "角色目标",
                "conflict": "主要冲突或阻碍",
                "outcome": "节点结果",
                "nextHook": "下一节点衔接线索"
              }}
            ]
          }}
        }}

        约束：
        1. 至少输出 3 个节点，按时间推进顺序排列。
        2. 节点内容必须可用于引导剧情，不要空洞描述。
        3. timePoint 要与首屏重要时间点保持一致或可映射。
        4. 允许树结构分支：主线节点 parentId 为空，分支节点 parentId 指向父节点 id。
        5. 每个节点必须给出唯一 id。
        6. 时间最前的第一个节点必须是根节点；后续时间点默认接在前一节点下。
        7. 同一时间点的并行节点要挂在同一父节点下，表示“同时发展”的分叉。
        8. 若时间从“多年以前/三年前/童年回忆”等明显跳到“当前/此刻/今夜/次日”，应开启新主线根节点（parentId 为空）。
        9. 节点字段务必短句化：title/timePoint <= 20 字；trigger/objective/conflict/outcome/nextHook <= 40 字；event <= 80 字。

        已抽取角色：
        {_json_preview(characters, None)}

        已抽取首屏时间点：
        {_json_preview(openings, None)}

        已抽取地点条目：
        {_json_preview(locations, None)}

        故事摘要：
        {_trim(story_summary, None) or "无"}

        故事原文全文（必须参考，不可忽略）：
        {_trim(story_text, None) or "无"}

        当前草稿上下文：
        {build_context(draft)}
        """
    )


def build_timeline_bridge_decision_prompt(
    anchor_node: dict[str, object],
    candidate_nodes: list[dict[str, object]],
) -> str:
    return dedent(
        f"""
        你是剧情时间线结构审校器。你需要判断“新分段中的根节点”是否应该连接到“上一段末尾锚点节点”之后。
        你的目标是保持时间顺序合理：顺叙应连接；明显倒叙/回忆/平行线可不连接。

        输入：
        - anchorNode: 上一段末尾锚点
        - candidateRoots: 当前分段中待判断的根节点（无父节点）

        请输出严格 JSON（不要 markdown，不要解释）：
        {{
          "decisions": [
            {{
              "nodeId": "候选节点ID",
              "bridgeToAnchor": true
            }}
          ]
        }}

        约束：
        1. nodeId 必须来自 candidateRoots。
        2. bridgeToAnchor=true 表示将该节点 parentId 设为 anchorNode.id。
        3. bridgeToAnchor=false 表示保持该节点为独立根节点。
        4. 若信息不足，优先 true（保持主线连续）。

        anchorNode:
        {_json_preview(anchor_node, None)}

        candidateRoots:
        {_json_preview(candidate_nodes, None)}
        """
    )


def build_timeline_organize_prompt(
    timeline: dict[str, object],
    draft: dict[str, object],
) -> str:
    nodes = timeline.get("nodes", []) if isinstance(timeline, dict) else []
    return dedent(
        f"""
        你是剧情时间线总编。你需要“重排 + 重写 + 统一时间格式”，输出一个可应用的时间线提案。
        输出必须是严格 JSON，不要 markdown，不要解释，不要额外文字。

        目标：
        1. 全部节点采用同一时间基准：T0（当前主线时刻）。
        2. 全部 timePoint 采用统一格式：`T±<offset> | <时间描述>`。
        3. 按时间顺序重排节点；明显回忆段可以在前，但切回当前主线时必须另起根节点。
        4. 修复 parentId：禁止环、禁止无效父节点；同一阶段分支要挂在同一父节点下。
        5. 压缩文本：节点内容简洁可执行，不写长散文。

        输出 JSON 结构：
        {{
          "timeBaseline": "T0=当前主线时刻（一句话说明）",
          "timeFormat": "T±<offset> | 时间描述",
          "nodes": [
            {{
              "id": "可沿用旧ID，若冲突可重命名",
              "parentId": "父节点ID，根节点为空字符串",
              "title": "节点标题（<=24字）",
              "timePoint": "T-3Y | 三年前",
              "trigger": "触发条件（<=48字）",
              "event": "关键事件（<=96字）",
              "objective": "角色目标（<=56字）",
              "conflict": "主要冲突（<=56字）",
              "outcome": "节点结果（<=56字）",
              "nextHook": "下一线索（<=48字）"
            }}
          ]
        }}

        额外约束：
        - 节点数量 3-12。
        - 若原节点已足够好，允许仅做轻微重写与排序。
        - 尽量保留原节点语义，不随意删除关键事件。

        当前时间线：
        {_json_preview(nodes, None)}

        当前草稿上下文：
        {build_context(draft)}
        """
    )
