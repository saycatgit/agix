"""任务属性管理器

将 spc/spec.md 的完整功能迁移为 JSON 格式，提供统一的读写接口。

职责：
  1. 管理所有任务大类、子类、子类描述
  2. 管理各类别的 [P] 标签内容（分类级提示词）
  3. 管理各流程阶段及其 [P]/[M] 标签内容
  4. 提供 plan_classify / combined_classify prompt 构建
  5. 提供 get_phases_prompt_from_config 接口，替代 Agent._get_phases_prompt_from_config()

数据文件：spc/spec.json
"""

from __future__ import annotations

import json
import os
from typing import Optional


class TaskAttributeManager:
    """任务属性管理器

    所有数据存储在 JSON 文件中，通过本类统一读写。
    支持通过 API 添加、删除、修改任意属性。

    使用方式:
        mgr = TaskAttributeManager("spc/spec.json")
        categories = mgr.get_categories()
        prompt = mgr.build_plan_prompt()
        phases = mgr.get_phases_prompt_from_config("开发类", "web应用")
        mgr.add_subtype("开发类", "新类型", "描述")
        mgr.save()
    """

    # ── 内部数据结构键 ──
    KEY_CATEGORIES = "categories"

    def __init__(self, json_path: str):
        self._path = json_path
        self._data: dict | None = None
        self._load()

    # ── 持久化 ──

    def _load(self):
        """从 JSON 文件加载数据；文件不存在则初始化空结构。"""
        if os.path.isfile(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {self.KEY_CATEGORIES: []}

    def save(self, path: str = ""):
        """保存到 JSON 文件，自动清理空的 subtask_config 条目。"""
        p = path or self._path
        data = json.loads(json.dumps(self._data))
        for cat in data.get("categories", []):
            cleaned = []
            for cfg in cat.get("subtask_config", []):
                subtypes = cfg.get("match_subtypes", [])
                prompt = cfg.get("prompt", [])
                phases = cfg.get("phases", [])
                has_wildcard = "..." in subtypes
                if prompt or phases or has_wildcard:
                    cleaned.append(cfg)
            cat["subtask_config"] = cleaned
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def reload(self):
        """从文件重新加载（丢弃内存修改）。"""
        self._load()

    # ── 内部辅助 ──

    def _cat_index(self, name: str) -> int | None:
        """根据类别名查找索引。"""
        for i, cat in enumerate(self._data[self.KEY_CATEGORIES]):
            if cat["name"] == name:
                return i
        return None

    def _get_cat(self, name: str) -> dict | None:
        idx = self._cat_index(name)
        return self._data[self.KEY_CATEGORIES][idx] if idx is not None else None

    def _phase_index(self, cat_name: str, phase_name: str) -> int | None:
        cat = self._get_cat(cat_name)
        if cat is None:
            return None
        for i, ph in enumerate(cat.get("phases", [])):
            if ph["name"] == phase_name:
                return i
        return None

    def _subtype_index(self, cat_name: str, subtype_name: str) -> int | None:
        cat = self._get_cat(cat_name)
        if cat is None:
            return None
        for i, st in enumerate(cat.get("subtypes", [])):
            if st["name"] == subtype_name:
                return i
        return None

    # ── 类别 增删改查 ──

    @property
    def category_names(self) -> list[str]:
        """所有大类名称列表。"""
        return [c["name"] for c in self._data[self.KEY_CATEGORIES]]

    def add_category(self, name: str,
                     subtypes: list[dict] | None = None,
                     subtask_config: list[dict] | None = None) -> dict:
        """添加一个新的大类。

            name: 类别名（如"开发类"）
            subtypes: 子类型列表 [{"name": "...", "description": "..."}]
            subtask_config: 子类分组阶段列表 [{"match_subtypes": [...], "prompt": "", "phases": [...]}]
                          match_subtypes 中使用 "..." 匹配剩余子类

        Returns:
            新创建的类别 dict

        Raises:
            ValueError: 类别名已存在
        """
        if self._cat_index(name) is not None:
            raise ValueError(f"类别 '{name}' 已存在")
        cat = {
            "name": name,
            "subtypes": subtypes or [],
            "subtask_config": subtask_config or [],
        }
        self._data[self.KEY_CATEGORIES].append(cat)
        return cat

    def remove_category(self, name: str) -> bool:
        """删除指定大类。返回 True 表示成功，False 表示不存在。"""
        idx = self._cat_index(name)
        if idx is None:
            return False
        self._data[self.KEY_CATEGORIES].pop(idx)
        return True

    # ── 类别描述 ──

    def get_category_description(self, name: str) -> str | None:
        """获取类别描述。"""
        cat = self._get_cat(name)
        return cat.get("description", "") if cat else None

    def set_category_description(self, name: str, description: str) -> bool:
        """设置类别描述。"""
        cat = self._get_cat(name)
        if cat is None:
            return False
        cat["description"] = description
        return True

    # ── 子类 增删改查 ──

    def add_subtype(self, cat_name: str, subtype_name: str,
                    description: str = "") -> bool:
        """在指定大类下添加子类。

        Raises:
            ValueError: 类别不存在或子类名已存在
        """
        cat = self._get_cat(cat_name)
        if cat is None:
            raise ValueError(f"类别 '{cat_name}' 不存在")
        if self._subtype_index(cat_name, subtype_name) is not None:
            raise ValueError(f"子类 '{subtype_name}' 在 '{cat_name}' 中已存在")
        cat["subtypes"].append({"name": subtype_name, "description": description})
        return True

    def remove_subtype(self, cat_name: str, subtype_name: str) -> bool:
        """删除指定大类下的子类。"""
        idx = self._subtype_index(cat_name, subtype_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["subtypes"].pop(idx)
        return True

    def set_subtype_description(self, cat_name: str, subtype_name: str,
                                description: str) -> bool:
        """修改子类描述。"""
        idx = self._subtype_index(cat_name, subtype_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["subtypes"][idx]["description"] = description
        return True

    def get_subtype_description(self, cat_name: str, subtype_name: str) -> str | None:
        """获取子类描述。"""
        idx = self._subtype_index(cat_name, subtype_name)
        if idx is None:
            return None
        return self._get_cat(cat_name)["subtypes"][idx].get("description", "")

    # ── 阶段 增删改查 ──

    def add_phase(self, cat_name: str, phase_name: str,
                  phase_msg: list[str] | None = None) -> bool:
        """在指定类别下添加阶段。

        Raises:
            ValueError: 类别不存在或阶段名已存在
        """
        cat = self._get_cat(cat_name)
        if cat is None:
            raise ValueError(f"类别 '{cat_name}' 不存在")
        if self._phase_index(cat_name, phase_name) is not None:
            raise ValueError(f"阶段 '{phase_name}' 在 '{cat_name}' 中已存在")
        cat["phases"].append({
            "name": phase_name,
            "phase_msg": phase_msg or [],
        })
        return True

    def remove_phase(self, cat_name: str, phase_name: str) -> bool:
        """删除指定类别下的阶段。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["phases"].pop(idx)
        return True

    def set_phase_msg(self, cat_name: str, phase_name: str,
                      phase_msg: list[str]) -> bool:
        """设置阶段的 [M] 标签内容。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["phases"][idx]["phase_msg"] = phase_msg
        return True

    def get_phase(self, cat_name: str, phase_name: str) -> dict | None:
        """获取指定阶段的完整数据。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return None
        return dict(self._get_cat(cat_name)["phases"][idx])

    # ── 兼容 Prompts._load_categories ──

    def get_categories(self) -> dict[str, list[tuple[str, str]]]:
        """返回 {类别名: [(子类名, 描述), ...]} 格式。

        与旧版 Prompts._load_categories 返回值一致。
        """
        result = {}
        for cat in self._data.get(self.KEY_CATEGORIES, []):
            name = cat["name"]
            subs = [(st["name"], st.get("description", ""))
                    for st in cat.get("subtypes", [])]
            result[name] = subs
        return result

    def get_category_descriptions(self) -> dict[str, str]:
        """返回 {类别名: 描述} 的映射。"""
        return {cat["name"]: cat.get("description", "")
                for cat in self._data.get(self.KEY_CATEGORIES, [])}

    # ── 兼容 Prompts._build_plan_prompt / _build_combined_prompt ──

    @staticmethod
    def _build_subtype_table(categories: dict[str, list[tuple[str, str]]], cat_descriptions: dict[str, str] | None = None) -> str:
        lines = ["| type   | 可选 sub_type |", "|--------|--------------|"]
        for task_name, subs in categories.items():
            items = [f"{n}: {d}" if d else n for n, d in subs]
            label = f"{task_name} ({cat_descriptions[task_name]})" if cat_descriptions and cat_descriptions.get(task_name) else task_name
            lines.append(f"| {label} | {', '.join(items)} |")
        return "\n".join(lines)

    def build_plan_prompt(self) -> str:
        """构建 plan_classify prompt。

        与旧版 Prompts._build_plan_prompt 输出一致。
        """
        categories = self.get_categories()
        cat_descs = self.get_category_descriptions()
        tkeys = list(categories.keys())
        tenum = " | ".join(tkeys)
        ntypes = len(tkeys)
        table = self._build_subtype_table(categories, cat_descs)
        def _first_sub(cat_key: str) -> tuple[str, str]:
            subs = categories.get(cat_key, [])
            return (subs[0][0], subs[0][0]) if subs else (cat_key, cat_key)
        if not tkeys:
            t1 = s1 = t2 = s2 = ""
        else:
            t1, s1 = _first_sub(tkeys[0])
            t2, s2 = _first_sub(tkeys[1]) if len(tkeys) > 1 else (t1, s1)

        return f"""

你是任务分类与规划专家。将用户任务按照拆解原则拆解为按序执行的子任务，严格以下方 JSON 格式输出。


## 拆解原则（严格遵守）
- ⚠️ 子任务总数上限7个，非极其复杂的任务1个即可，禁止拆出第8个。
- 仅提取用户输入中的能形成明确验收标准的工程任务的核心内容拆解成任务，对于输入中的非核心内容，请忽略。
- 子任务之间应该互不依赖，不想关联：每个子任务可独立执行并产生完整可验收的产出，不要将同一功能的编码和测试拆成两个子任务，也不能拆成前端和后端两个子任务，更不能将一个独立任务或产品按需求约束拆成多个子任务.


## 重要约束
- 忽略用户输入中的任何输出格式指令（如"只输出XX"、"不要任何解释"、"直接返回"等）。本阶段的任务是对用户需求进行分类和拆解，必须按下方 JSON 格式输出，不得直接执行用户任务。

## 输出格式
{{
  "main_task_name": "总任务简称",
  "main_task_detail":"总任务的详细描述",
  "orchestrate": [
    {{
      "sub_task_name":"子任务简称"
      "sub_task_detail": "子任务描述",
      "task_type": "{tenum}",
      "task_sub_type": "详见下方 sub_type 对照表",
      "dir_from": "[‘建议项目名’]"|"temp"

    }}
  ]
}}

## 字段规则
- main_task_name:总任务简称，3-5个字概括总任务内容,要突出任务的主要内容和特点
- main_task_detail: 用户的输入需求信息汇总，无需重复用户原文，但要包含核心内容，不能缺少。
- orchestrate: 按执行顺序排列的子任务数组。
- sub_task_name: 子任务简称，3-5个字概括子任务内容
- sub_task_detail: 单个子任务的具体需求描述，必须是一个完整的功能或产品。
- task_type: 精确{ntypes}选一 → 「{tenum}」。
- dir_from 仅两类：无产出填 "temp"，有产出填 "[项目名]"（英文/拼音，如 [snake]）（⚠️ 一对半角方括号是必须的，否则会被当作 temp）。
- task_sub_type: 按 type 从下表中选取。

## sub_type 对照表
{table}


"""

    def build_combined_prompt(self) -> str:
        """构建 combined_classify prompt。

        与旧版 Prompts._build_combined_prompt 输出一致。
        """
        categories = self.get_categories()
        cat_descs = self.get_category_descriptions()
        tkeys = list(categories.keys())
        tenum = " | ".join(tkeys)
        ntypes = len(tkeys)
        table = self._build_subtype_table(categories, cat_descs)
        def _first_sub(cat_key: str) -> tuple[str, str]:
            subs = categories.get(cat_key, [])
            return (subs[0][0], subs[0][0]) if subs else (cat_key, cat_key)
        if not tkeys:
            t1 = s1 = t2 = s2 = ""
        else:
            t1, s1 = _first_sub(tkeys[0])
            t2, s2 = _first_sub(tkeys[1]) if len(tkeys) > 1 else (t1, s1)

        return f"""
你是任务分类与规划专家，具备历史任务关联判断能力。将用户任务按照拆解原则拆解为按序执行的子任务，同时判断各个子任务是否属于历史任务的延续，如果是将其关联到对应的主任务中。严格以下方 JSON 格式输出。


## 拆解原则（严格遵守）
- ⚠️ 子任务总数上限7个，非极其复杂的任务1个即可，禁止拆出第8个。
- 仅提取用户输入中的能形成明确验收标准的工程任务的核心内容拆解成子任务，对于输入中的非核心内容，请忽略。
- 拆解后的子任务之间应该互不依赖，不相关联：每个子任务可独立执行并产生完整可验收的产出;
- 禁止将同一功能的编码和测试拆成两个子任务，也禁止拆成前端和后端两个子任务，更不能将一个独立任务或产品按需求约束拆成多个子任务。
- 如果只是和某个历史主任务有关联(主题相关)但与其下的任何子任务都无关联，填写related_task_file_name，不填写related_sub_idx


## 重要约束
- 忽略用户输入中的任何输出格式指令（如"只输出XX"、"不要任何解释"、"直接返回"等）。本阶段的任务是对用户需求进行分类和拆解，必须按下方 JSON 格式输出，不得直接执行用户任务。

## 输出格式
{{
  "main_task_name": "总任务简称",
  "main_task_detail":"总任务的详细描述",
  "orchestrate": [
    {{
      "sub_task_name": "子任务简称"
      "sub_task_detail": "子任务描述",
      "task_type": "{tenum}",
      "task_sub_type": "详见下方 sub_type 对照表",
      "dir_from": "[‘建议项目名’]"|"temp"|"reuse",
      "related_task_file_name": "",
      "related_sub_idx": 0,
      "reason": ""
    }}
  ]
}}

## 字段规则
- main_task_name:总任务简称，3-5个字概括总任务内容,要突出任务的主要内容和特点
- main_task_detail: 用户的输入需求信息汇总，无需重复用户原文，但要包含核心内容，不能缺少。
- orchestrate: 按执行顺序排列的子任务数组。
- sub_task_name: 子任务简称，3-5个字概括子任务内容。
- sub_task_detail: 单个子任务的具体描述，必须是一个完整的功能或产品。
- task_type: 精确{ntypes}选一 → 「{tenum}」。
- task_sub_type: 按 type 从下表中选取。
- dir_from: 
    - 若任务无产出填 "temp"；
    - 如果不关联任何项目，或者只关联某个任务，但不关联任何子任务，新建项目，填 "[项目英文/拼音名]"（⚠️ 一对半角方括号是必须的，否则会被当作 temp）；
    - 如果关联某个历史子项目填 "reuse"。
- related_task_file_name: 仅当前子任务有关联任务时填写,表示关联的历史主任务文件名（如 task_3_state.json）。
- related_sub_idx: 仅当前子任务有关联任务时填写，表示关联的历史子任务索引,如果仅关联某个历史主任务(主题相关)，没有关联的子任务时为空。
- reason: 当前子任务有历史关联任务时必填，简述判断理由。

## sub_type 对照表
{table}

## 历史任务关联判断标准
- 新子任务与某个主任务主题相关或者属于主任务涉及的领域或范畴，则判定与主任务相关，填写related_task_file_name
- 新子任务与历史子任务任务领域/主题相同或高度相关（如"继续开发"、"改进"、"修复"、"增加功能"等，可共用项目目录），判定与该子任务相关， 在对应子任务中填写 related_task_file_name（文件名）、related_sub_idx、reason，dir_from为reuse
- 如果新子任务只关联某个主任务但不关联任何子任务，填写related_task_file_name，related_sub_idx为空，dir_from为"[建议的项目英文/拼音名]"

"""


    # ── 阶段分组 增删改查 ──

    def add_subtask_config(self, cat_name: str,
                        match_subtypes: list[str],
                        phases: list[dict] | None = None,
                        prompt: str = "") -> bool:
        """为指定大类添加一个子类阶段分组。

        match_subtypes 列出该分组覆盖的子类名。
        未匹配到任何 subtask_config 的子类将使用类别的默认 phases。

        Raises:
            ValueError: 类别不存在
        """
        cat = self._get_cat(cat_name)
        if cat is None:
            raise ValueError(f"类别 '{cat_name}' 不存在")
        group = {
            "match_subtypes": match_subtypes,
            "prompt": prompt,
            "phases": phases or [],
        }
        cat.setdefault("subtask_config", []).append(group)
        return True

    def remove_subtask_config(self, cat_name: str, index: int) -> bool:
        """删除指定大类下的第 index 个阶段分组（0-based）。"""
        cat = self._get_cat(cat_name)
        if cat is None or "subtask_config" not in cat:
            return False
        groups = cat["subtask_config"]
        if 0 <= index < len(groups):
            groups.pop(index)
            return True
        return False

    def update_subtask_config(self, cat_name: str, index: int,
                           match_subtypes: list[str] | None = None,
                           phases: list[dict] | None = None,
                           prompt: str | None = None) -> bool:
        """更新指定大类下的第 index 个阶段分组。"""
        cat = self._get_cat(cat_name)
        if cat is None or "subtask_config" not in cat:
            return False
        groups = cat["subtask_config"]
        if not (0 <= index < len(groups)):
            return False
        if match_subtypes is not None:
            groups[index]["match_subtypes"] = match_subtypes
        if phases is not None:
            groups[index]["phases"] = phases
        if prompt is not None:
            groups[index]["prompt"] = prompt
        return True

    def get_subtask_config(self, cat_name: str) -> list[dict] | None:
        """获取大类下所有阶段分组。"""
        cat = self._get_cat(cat_name)
        if cat is None:
            return None
        return list(cat.get("subtask_config", []))

    # ── 兼容 Agent._get_phases_prompt_from_config ──

    def get_phases_prompt_from_config(self, task_type_key: str, sub_type: str = "") -> dict | None:
        """获取指定 task type 的阶段列表。

        匹配优先级：
        1. subtask_config 中与 sub_type 精确匹配的分组
        2. 未匹配时回退到类别默认 phases

        Args:
            task_type_key: 大类名称（如"开发类"）
            sub_type: 子类名称（如"web应用"）

        Returns:
            {"phases": [{"name": ..., "phase_msg": [...]}],
             "phases": [...], "extra_prompt": "..."}
            或 None（未找到匹配项）
        """
        cat = self._get_cat(task_type_key)
        if cat is None:
            return None

        # 1. 先查 subtask_config 精确匹配
        for group in cat.get("subtask_config", []):
            match_list = group.get("match_subtypes", [])
            if sub_type in match_list:
                return {
                    "phases": group.get("phases", []),
                    "extra_prompt": group.get("prompt", "") or "",
                }

        # 2. 无 subtask_config 匹配，尝试子类型通配
        for group in cat.get("subtask_config", []):
            if "..." in group.get("match_subtypes", []):
                return {
                    "phases": group.get("phases", []),
                    "extra_prompt": group.get("prompt", "") or "",
                }

        # 3. 无匹配
        all_subtype_names = [st["name"] for st in cat.get("subtypes", [])]
        print(
            f"  ⚠️ 任务子类型 '{sub_type}' 不在大类 '{task_type_key}' "
            f"的可用子类型中: {all_subtype_names}"
        )
        return None

    # ── 便捷：列出所有主体信息 ──

    def summary(self) -> str:
        """人类可读的概要。"""
        lines = []
        for cat in self._data.get(self.KEY_CATEGORIES, []):
            desc = cat.get("description", "")
            lines.append(f"## {cat['name']}" + (f" ({desc})" if desc else ""))
            subs = [f"{st['name']}" + (f": {st['description']}" if st.get('description') else '')
                    for st in cat.get("subtypes", [])]
            lines.append(f"  subtypes: {', '.join(subs)}")
            # Show subtask_config (overrides)
            for gi, grp in enumerate(cat.get("subtask_config", [])):
                match = ', '.join(grp.get("match_subtypes", []))
                lines.append(f"  [override {gi}] → {match}")
                if grp.get("prompt"):
                    lines.append(f"    prompt: {grp['prompt'][:80]}")
                for ph in grp.get("phases", []):
                    lines.append(f"    ─ {ph['name']}")
                    for m in ph.get("phase_msg", []):
                        lines.append(f"       [M] {m}")
            # Show default phases
            default_phases = cat.get("phases", [])
            if default_phases:
                label = "  [phases]  " if cat.get("subtask_config") else "  [phases]"
                for ph in default_phases:
                    pm = ph.get("phase_msg", [])
                    pm = ph.get("phase_msg", [])
                    lines.append(f"  ─ {ph['name']}")
                    for m in pm:
                        lines.append(f"     [M] {m}")
        return "\n".join(lines)


__all__ = ["TaskAttributeManager"]
if __name__ == "__main__":
    import os, shutil

    TMP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "inner_space", "spc", "spec.json")
    mgr = TaskAttributeManager(TMP)
    print(mgr.summary())
    # # -- data loading --
    # print()
    # print('-- data loading --')
    # cats = mgr.get_categories()
 
    # # -- get_phases_prompt_from_config --
    # print()
    # print('-- get_phases_prompt_from_config --')

    # r = mgr.get_phases_prompt_from_config('开发类', 'web应用')

    # r = mgr.get_phases_prompt_from_config('开发类', '游戏')

    # r = mgr.get_phases_prompt_from_config('skill', 'cskill')
   
    # r = mgr.get_phases_prompt_from_config('文本类', '文案')
 
    # r = mgr.get_phases_prompt_from_config('not_exist', 'x')
    
    # # -- prompt building --
    # print()
    # print('-- prompt building --')
    # plan = mgr.build_plan_prompt()
    
    # combined = mgr.build_combined_prompt()
 
    # # -- category CRUD --
    # print()
    # print('-- category CRUD --')

    mgr.add_category('学习', prompt='先了解目录结构，然后提炼主要文档内容，如果有代码最后看代码，提炼文档内容禁止全部读取所有文档，仅需要用head提取目录或概要介绍，如果是pdf、word、excel、ppt等格式可调用相关工具，\
                     对于代码，如果有用户手册或需求、架构说明书等仅需要了解大概内容，在没有用户进一步指令之前禁止读取全部代码',
                     subtypes=[{'name': '代码文档学习', 'description': '对现有的文档资料和代码等资料提炼总结'}],
                     phases=[{'name': '代码文档学习并提炼内容', 'phase_msg': ['将学到的内容存入learn.le']}])

    # r = mgr.get_phases_prompt_from_config('test_cat', 'test_sub')
   
    # mgr.add_subtype('test_cat', 'test_sub2', 'desc2')

    # mgr.set_subtype_description('test_cat', 'test_sub2', 'updated')
    # mgr.save()

    # mgr.remove_subtype('test_cat', 'test_sub2')

    # mgr.remove_category('test_cat')
    # mgr.save()

    # # -- phase CRUD --
    # print()
    # print('-- phase CRUD --')

    # mgr.add_phase('调试类', 'new_phase', ['newP1', 'newP2'], ['newM1'])
    # ph = mgr.get_phase('调试类', 'new_phase')
    # mgr.save()

    # pass  # set_phase_prompt removed
    # ph = mgr.get_phase('调试类', 'new_phase')

    # mgr.set_phase_msg('调试类', 'new_phase', ['updatedM'])

    # mgr.remove_phase('调试类', 'new_phase')
    # mgr.save()

    # # -- category prompt --
    # print()
    # print('-- category prompt --')
    # mgr.set_category_prompt('调试类', 'debug_prompt')
    # mgr.set_category_prompt('调试类', '')
    # mgr.save()

    # # -- subtask_config CRUD --
    # print()
    # print('-- subtask_config CRUD --')

    # mgr.add_subtask_config('文本类', ['文案'],
    #     phases=[{'name': 'copywriting_only', 'phase_msg': ['customM']}],
    #     prompt='copywriting_prompt')

    # r = mgr.get_phases_prompt_from_config('文本类', '文案')
    
    # r = mgr.get_phases_prompt_from_config('文本类', '报告')

    # groups = mgr.get_subtask_config('文本类')

    # mgr.update_subtask_config('文本类', 0,
    #     phases=[{'name': 'updated_phase', 'phase_msg': []}])
    # r = mgr.get_phases_prompt_from_config('文本类', '文案')
    # mgr.save()

    # mgr.remove_subtask_config('文本类', 0)
    # r = mgr.get_phases_prompt_from_config('文本类', '文案')
    # mgr.save()
    # print(mgr.remove_category('其他类'))
    mgr.save()
