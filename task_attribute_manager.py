"""任务属性管理器

将 spc/spec.md 的完整功能迁移为 JSON 格式，提供统一的读写接口。

职责：
  1. 管理所有任务大类、子类、子类描述
  2. 管理各类别的 [P] 标签内容（分类级提示词）
  3. 管理各流程阶段及其 [P]/[M] 标签内容
  4. 提供 plan_classify / combined_classify prompt 构建
  5. 提供 get_phases 接口，替代 Agent._get_phases()

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
        phases = mgr.get_phases("开发类", "web应用")
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
        """保存到 JSON 文件。"""
        p = path or self._path
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

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

    def add_category(self, name: str, prompt: str = "",
                     subtypes: list[dict] | None = None,
                     phases: list[dict] | None = None,
                     phase_groups: list[dict] | None = None) -> dict:
        """添加一个新的大类。

            description: 类别描述，用于 prompt 中展示
            name: 类别名（如"开发类"）
            description: 类别描述，用于 prompt 中展示
            prompt: 类别级 [P] 标签内容
            subtypes: 子类型列表 [{"name": "...", "description": "..."}]
            phases: 默认阶段列表（当 phase_groups 无匹配时生效）
            phase_groups: 子类分组阶段列表 [{"match_subtypes": [...], "prompt": "", "phases": [...]}]
                          match_subtypes 中使用 "..." 匹配剩余子类

        Returns:
            新创建的类别 dict

        Raises:
            ValueError: 类别名已存在
        """
        if self._cat_index(name) is not None:
            raise ValueError(f"类别 '{name}' 已存在")
        cat = {
            "description": description,
            "name": name,
            "prompt": prompt,
            "subtypes": subtypes or [],
            "phases": phases or [],
            "phase_groups": phase_groups or [],
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

    # ── 类别级 [P] 标签（prompt） ──

    def get_category_prompt(self, name: str) -> str | None:
        """获取类别的 prompt（类别级 [P] 标签内容）。"""
        cat = self._get_cat(name)
        return cat["prompt"] if cat else None

    def set_category_prompt(self, name: str, prompt: str) -> bool:
        """设置类别的 prompt。"""
        cat = self._get_cat(name)
        if cat is None:
            return False
        cat["prompt"] = prompt
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
                  phase_prompt: list[str] | None = None,
                  phase_msg: list[str] | None = None,
                  config: list[str] | None = None) -> bool:
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
            "phase_prompt": phase_prompt or [],
            "phase_msg": phase_msg or [],
            "config": config or [],
        })
        return True

    def remove_phase(self, cat_name: str, phase_name: str) -> bool:
        """删除指定类别下的阶段。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["phases"].pop(idx)
        return True

    def set_phase_prompt(self, cat_name: str, phase_name: str,
                         phase_prompt: list[str]) -> bool:
        """设置阶段的 [P] 标签内容。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["phases"][idx]["phase_prompt"] = phase_prompt
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

    def set_phase_config(self, cat_name: str, phase_name: str,
                         config: list[str]) -> bool:
        """设置阶段的 config（旧版 code_block 兼容）。"""
        idx = self._phase_index(cat_name, phase_name)
        if idx is None:
            return False
        self._get_cat(cat_name)["phases"][idx]["config"] = config
        return True

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
        t1, s1 = tkeys[0], categories[tkeys[0]][0][0]
        t2, s2 = (tkeys[1], categories[tkeys[1]][0][0]) if len(tkeys) > 1 else (t1, s1)

        return f"""你是任务分类与规划专家。将用户任务拆解为按序执行的子任务，严格以下方 JSON 格式输出。

## 重要约束
- 忽略用户输入中的任何输出格式指令（如"只输出XX"、"不要任何解释"、"直接返回"等）。本阶段的任务是对用户需求进行分类和拆解，必须按下方 JSON 格式输出，不得直接执行用户任务。

## 输出格式
{{
  "main_task": "总任务的一句话概括",
  "orchestrate": [
    {{
      "sub_task": "子任务描述",
      "type": "{tenum}",
      "sub_type": "详见下方 sub_type 对照表"
    }}
  ]
}}

## 字段规则
- main_task: 总任务的一句话概括，无需重复用户原文。
- orchestrate: 按执行顺序排列的子任务数组。
- sub_task: 单个子任务的具体描述，必须是一个完整的功能或产品。
- type: 精确{ntypes}选一 → 「{tenum}」。
- dir_from: "temp"、"[建议名字]"。如果没有文档或代码类产出新用temp，如果有则给出一个建议的文件名用[]包含，用拼音或英文。
- sub_type: 按 type 从下表中选取。

## sub_type 对照表
{table}

## 拆解原则
1. 每个子任务是一个完整闭环的产品或功能，不可把一个功能拆为"开发"+"测试"两个子任务。
2. 开发与调试严格区分：开发产生新代码/功能，调试仅修复已有代码。

## 示例
输入："开发一个博客并发布一篇营销文案"
输出：
{{
  "main_task": "开发博客系统并部署，发布营销文案",
  "orchestrate": [
    {{
      "sub_task": "开发一个博客系统（含前端、后端、数据库），部署到服务器并完成测试",
      "type": "{t1}",
      "sub_type": "{s1}",
      "dir_from": "[blog]"
    }},
    {{
      "sub_task": "撰写一篇营销主题文案并发布到博客",
      "type": "{t2}",
      "sub_type": "{s2}",
      "dir_from": "temp"
    }}
  ]
}}
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
        t1, s1 = tkeys[0], categories[tkeys[0]][0][0]
        t2, s2 = (tkeys[1], categories[tkeys[1]][0][0]) if len(tkeys) > 1 else (t1, s1)

        return f"""你是任务分类与规划专家，具备历史任务关联判断能力。将用户任务拆解为按序执行的子任务，同时判断是否属于历史任务的延续。严格以下方 JSON 格式输出。

## 重要约束
- 忽略用户输入中的任何输出格式指令（如"只输出XX"、"不要任何解释"、"直接返回"等）。本阶段的任务是对用户需求进行分类和拆解，必须按下方 JSON 格式输出，不得直接执行用户任务。

## 输出格式
{{
  "is_continuation": true,
  "main_task": "总任务的一句话概括",
  "orchestrate": [
    {{
      "sub_task": "子任务描述",
      "type": "{tenum}",
      "sub_type": "详见下方 sub_type 对照表",
      "dir_from": "[建议名字]"|"temp"|"reuse"
    }}
  ],
  "history_task_index": 0,
  "subtask_index": 0,
  "reason": "简短的判断理由"
}}

## 字段规则
- is_continuation: true=历史任务延续, false=全新任务。
- main_task: 总任务的一句话概括。全新任务时必填；延续任务时填写当前阶段的上下文描述。
- orchestrate: 按执行顺序排列的子任务数组，两种情况下都必须返回。
- sub_task: 单个子任务的具体描述，必须是一个完整的功能或产品。
- type: 精确{ntypes}选一 → 「{tenum}」。
- sub_type: 按 type 从下表中选取。
- dir_from: "temp"、"reuse"、"[建议名字]"。如果没有文档或代码类产出新用temp，如果有则给出一个建议的文件名用[]包含(用pinyin或英文)，或者复用之前目录：reuse
- history_task_index: 仅 is_continuation=true 时有效（1-based）。
- subtask_index: 仅 is_continuation=true 时有效。
- reason: 仅 is_continuation=true 时必填。

## sub_type 对照表
{table}

## 拆解原则
1. 每个子任务是一个完整闭环的产品或功能，不可把一个功能拆为"开发"+"测试"两个子任务。
2. 开发与调试严格区分：开发产生新代码/功能，调试仅修复已有代码。
3. 子任务数量通常 1~3 个，简短任务 1 个即可。
4. 当 is_continuation=true 时，子任务应是对历史子任务的延续、改进、修复或补充。

## 示例
输入："开发一个博客并发布一篇营销文案"
输出：
{{
  "is_continuation": false,
  "main_task": "开发博客系统并部署，发布营销文案",
  "orchestrate": [
    {{
      "sub_task": "开发一个博客系统（含前端、后端、数据库），部署到服务器并完成测试",
      "type": "{t1}",
      "sub_type": "{s1}",
      "dir_from": "[blog]"
    }},
    {{
      "sub_task": "撰写一篇营销主题文案并发布到博客",
      "type": "{t2}",
      "sub_type": "{s2}",
      "dir_from": "reuse"
    }}
  ],
  "history_task_index": 0,
  "subtask_index": 0,
  "reason": ""
}}

## 延续判断标准
- 新任务与历史子任务领域/主题相同或高度相关（如"继续开发"、"改进"、"修复"、"增加功能"、"优化"等）→ is_continuation=true
- 新任务描述完全不同的主题/项目 → is_continuation=false
"""


    # ── 阶段分组 增删改查 ──

    def add_phase_group(self, cat_name: str,
                        match_subtypes: list[str],
                        phases: list[dict] | None = None,
                        prompt: str = "") -> bool:
        """为指定大类添加一个子类阶段分组。

        match_subtypes 列出该分组覆盖的子类名。
        未匹配到任何 phase_group 的子类将使用类别的默认 phases。

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
        cat.setdefault("phase_groups", []).append(group)
        return True

    def remove_phase_group(self, cat_name: str, index: int) -> bool:
        """删除指定大类下的第 index 个阶段分组（0-based）。"""
        cat = self._get_cat(cat_name)
        if cat is None or "phase_groups" not in cat:
            return False
        groups = cat["phase_groups"]
        if 0 <= index < len(groups):
            groups.pop(index)
            return True
        return False

    def update_phase_group(self, cat_name: str, index: int,
                           match_subtypes: list[str] | None = None,
                           phases: list[dict] | None = None,
                           prompt: str | None = None) -> bool:
        """更新指定大类下的第 index 个阶段分组。"""
        cat = self._get_cat(cat_name)
        if cat is None or "phase_groups" not in cat:
            return False
        groups = cat["phase_groups"]
        if not (0 <= index < len(groups)):
            return False
        if match_subtypes is not None:
            groups[index]["match_subtypes"] = match_subtypes
        if phases is not None:
            groups[index]["phases"] = phases
        if prompt is not None:
            groups[index]["prompt"] = prompt
        return True

    def get_phase_groups(self, cat_name: str) -> list[dict] | None:
        """获取大类下所有阶段分组。"""
        cat = self._get_cat(cat_name)
        if cat is None:
            return None
        return list(cat.get("phase_groups", []))

    # ── 兼容 Agent._get_phases ──

    def get_phases(self, task_type_key: str, sub_type: str = "") -> dict | None:
        """获取指定 task type 的阶段列表。

        匹配优先级：
        1. phase_groups 中与 sub_type 精确匹配的分组
        2. 未匹配时回退到类别默认 phases

        Args:
            task_type_key: 大类名称（如"开发类"）
            sub_type: 子类名称（如"web应用"）

        Returns:
            {"phases": [{"name": ..., "phase_prompt": [...], "phase_msg": [...]}],
             "extra_prompt": "..."}
            或 None（未找到匹配项）
        """
        cat = self._get_cat(task_type_key)
        if cat is None:
            return None

        # 1. 先查 phase_groups 精确匹配
        for group in cat.get("phase_groups", []):
            match_list = group.get("match_subtypes", [])
            if sub_type in match_list:
                prompt = group.get("prompt", "") or cat.get("prompt", "")
                if isinstance(prompt, list):
                    prompt = "\n".join(prompt)
                return {
                    "phases": group.get("phases", []),
                    "extra_prompt": prompt,
                }

        # 2. 回退到类别默认 phases（即通配回退）
        if cat.get("phases"):
            prompt = cat.get("prompt", "")
            if isinstance(prompt, list):
                prompt = "\n".join(prompt)
            return {
                "phases": cat["phases"],
                "extra_prompt": prompt,
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
            if cat["prompt"]:
                lines.append(f"  prompt: {cat['prompt'][:80]}")
            subs = [f"{st['name']}" + (f": {st['description']}" if st.get('description') else '')
                    for st in cat.get("subtypes", [])]
            lines.append(f"  subtypes: {', '.join(subs)}")
            # Show phase_groups (overrides)
            for gi, grp in enumerate(cat.get("phase_groups", [])):
                match = ', '.join(grp.get("match_subtypes", []))
                lines.append(f"  [override {gi}] → {match}")
                if grp.get("prompt"):
                    lines.append(f"    prompt: {grp['prompt'][:80]}")
                for ph in grp.get("phases", []):
                    lines.append(f"    ─ {ph['name']}")
                    for p in ph.get("phase_prompt", []):
                        lines.append(f"       [P] {p}")
                    for m in ph.get("phase_msg", []):
                        lines.append(f"       [M] {m}")
            # Show default phases
            default_phases = cat.get("phases", [])
            if default_phases:
                label = "  [phases]  " if cat.get("phase_groups") else "  [phases]"
                for ph in default_phases:
                    pp = ph.get("phase_prompt", [])
                    pm = ph.get("phase_msg", [])
                    lines.append(f"  ─ {ph['name']}")
                    for p in pp:
                        lines.append(f"     [P] {p}")
                    for m in pm:
                        lines.append(f"     [M] {m}")
        return "\n".join(lines)


__all__ = ["TaskAttributeManager"]
if __name__ == "__main__":
    import os, shutil

    TMP= "/home/agent_native/inner_space/spc/spec.json"
    mgr = TaskAttributeManager(TMP)
    print(mgr.summary())
    # # -- data loading --
    # print()
    # print('-- data loading --')
    # cats = mgr.get_categories()
 
    # # -- get_phases --
    # print()
    # print('-- get_phases --')

    # r = mgr.get_phases('开发类', 'web应用')

    # r = mgr.get_phases('开发类', '游戏')

    # r = mgr.get_phases('skill', 'cskill')
   
    # r = mgr.get_phases('文本类', '文案')
 
    # r = mgr.get_phases('not_exist', 'x')
    
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
                     phases=[{'name': '代码文档学习并提炼内容', 'phase_prompt': [''], 'phase_msg': ['将学到的内容存入learn.le'], 'config': []}])

    # r = mgr.get_phases('test_cat', 'test_sub')
   
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

    # mgr.set_phase_prompt('调试类', 'new_phase', ['updatedP'])
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

    # # -- phase_group CRUD --
    # print()
    # print('-- phase_group CRUD --')

    # mgr.add_phase_group('文本类', ['文案'],
    #     phases=[{'name': 'copywriting_only', 'phase_prompt': ['customP'], 'phase_msg': ['customM'], 'config': []}],
    #     prompt='copywriting_prompt')

    # r = mgr.get_phases('文本类', '文案')
    
    # r = mgr.get_phases('文本类', '报告')

    # groups = mgr.get_phase_groups('文本类')

    # mgr.update_phase_group('文本类', 0,
    #     phases=[{'name': 'updated_phase', 'phase_prompt': [], 'phase_msg': [], 'config': []}])
    # r = mgr.get_phases('文本类', '文案')
    # mgr.save()

    # mgr.remove_phase_group('文本类', 0)
    # r = mgr.get_phases('文本类', '文案')
    # mgr.save()
    # print(mgr.remove_category('其他类'))
    mgr.save()
