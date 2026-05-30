import os
import yaml
from jinja2 import Template
from flask import current_app


class PromptTemplateManager:
    _templates = {}
    _loaded = False

    BUILTIN_TEMPLATES = {
        'attribution_analysis': """你是一位资深教育分析专家。请基于以下学生错题数据进行归因分析。

## 学生错题数据
{{ data | default('无数据') }}

## 分析要求
请从以下维度进行归因分析，以JSON格式返回：
1. root_causes: 根因分类数组，每个包含 category(分类)、description(描述)、knowledge_points(涉及知识点)、confidence(置信度0-1)
2. knowledge_mastery: 知识点掌握度数组，每个包含 name(知识点名)、score(0-100)、trend(趋势up/down/stable)
3. ability_scores: 能力评分，包含 understanding(理解力)、calculation(计算力)、application(应用力)、reasoning(推理力)、memory(记忆力)，每项0-100
4. suggestions: 改进建议数组，每个包含 target(针对知识点)、action(行动建议)、priority(高/中/低)

注意：仅返回纯JSON，不要包含markdown代码块标记。""",

        'weak_point_prediction': """你是一位教育数据预测专家。请基于学生历史错题数据预测薄弱知识点和可能出错的题目。

## 历史错题数据
{{ data | default('无数据') }}

## 已有归因分析
{{ attribution | default('无') }}

## 预测要求
请以JSON格式返回：
1. weak_points: 薄弱知识点预测数组，每个包含 knowledge_point(知识点)、probability(概率0-1)、reasoning(推理依据)
2. error_predictions: 出错题目预测数组，每个包含 question_type(题型)、knowledge_point(知识点)、probability(概率0-1)、reason(预测原因)

注意：仅返回纯JSON。""",

        'error_question_prediction': """基于学生的学习薄弱点，预测可能出错的题目类型。

## 薄弱知识点
{{ weak_points | default('无') }}

## 错题历史
{{ history | default('无') }}

请以JSON格式返回出错题目预测数组，每个包含 question_type、difficulty、knowledge_point、probability(0-1)、reason。
注意：仅返回纯JSON。""",

        'learning_strategy': """你是一位学习策略规划专家。请基于以下分析结果为该学生制定个性化学习路径和复习策略。

## 归因分析结果
{{ attribution | default('无') }}

## 薄弱点预测
{{ prediction | default('无') }}

## 现有间隔复习计划
{{ review_plan | default('无') }}

## 策略要求
请以JSON格式返回：
1. learning_path: 学习路径数组，每个包含 knowledge_point(知识点)、priority(高/中/低)、estimated_minutes(预期耗时)
2. review_suggestions: 复习策略建议数组，每个包含 description(策略描述)、target_knowledge(针对知识点)、expected_effect(预期效果)
3. focus_directions: 重点突破方向数组(最多3个)，每个包含 direction(方向)、reason(原因说明)

注意：仅返回纯JSON。""",

        'explanation_generation': """你是一位优秀的学科教师。请为以下错题生成详细解析。

## 题目信息
题目类型：{{ question_type | default('未知') }}
难度：{{ difficulty | default('中等') }}
题目内容：{{ content | default('') }}
正确答案：{{ correct_answer | default('') }}
学生错误答案：{{ wrong_answer | default('') }}

## 解析要求
请以JSON格式返回：
1. thinking: 解题思路(字符串)
2. steps: 分步解答数组，每个包含 step(步骤编号)、content(步骤内容)
3. key_points: 关键知识点数组
4. pitfalls: 易错点提醒数组

注意：仅返回纯JSON。""",

        'variant_generation': """你是一位经验丰富的出题专家。请基于以下题目生成1-3道变式题。

## 原题信息
题目类型：{{ question_type | default('未知') }}
章节：{{ chapter | default('未知') }}
难度：{{ difficulty | default('中等') }}
题目内容：{{ content | default('') }}
正确答案：{{ correct_answer | default('') }}

## 变式题要求
- 保持相同知识点和难度水平
- 改变题目的具体情境或数字
- 须有明确的标准答案

请以JSON格式返回变式题数组，每个包含 content(题目内容)、option_a/b/c/d(选项)、correct_answer(正确答案)、analysis(解析)。
注意：仅返回纯JSON。""",

        'practice_generation': """你是一位练习题设计专家。请针对以下薄弱知识点生成3-5道巩固练习题。

## 薄弱知识点
{{ knowledge_point | default('未知') }}

## 知识点相关章节
{{ chapter | default('未知') }}

## 难度要求
{{ difficulty | default('中等') }}

## 练习题要求
- 涵盖该知识点的多个考查角度
- 难度从基础到提高递进

请以JSON格式返回练习题数组，每个包含 content、option_a/b/c/d、correct_answer、analysis、difficulty(1-4)。
注意：仅返回纯JSON。""",

        'chat_assistant': """你是一位专业的教育AI助手，擅长解答学习问题、分析错题原因、提供学习建议和知识讲解。

## 对话上下文
{{ history | default('无历史对话') }}

## 当前问题
{{ question | default('') }}

## 回答要求
- 回答准确、有教育意义
- 针对学生的问题给出清晰的解释
- 如涉及知识点，简要说明相关概念
- 如发现知识薄弱点，给出学习建议
- 回答简洁，重点突出""",

        'study_report': """你是一位教育数据分析专家。请基于以下分析数据为该学生生成学习报告。

## 归因分析结果
{{ attribution | default('无') }}

## 薄弱点预测
{{ prediction | default('无') }}

## 学习策略
{{ strategy | default('无') }}

## 报告周期
类型：{{ report_type | default('weekly') }}
起始：{{ period_start | default('未知') }}
结束：{{ period_end | default('未知') }}

## 报告要求
请以JSON格式返回：
1. summary: 学习概要(字符串，200字以内)
2. strengths: 进步与亮点数组，每个包含 description(描述)
3. weaknesses: 不足与问题数组，每个包含 description(描述)、knowledge_point(涉及知识点)
4. recommendations: 改进建议数组，每个包含 description(建议描述)、priority(高/中/低)
5. next_focus: 下阶段重点数组，每个包含 knowledge_point(知识点)、reason(原因)

注意：仅返回纯JSON。""",

        'study_plan': """你是一位学习计划规划专家。请基于以下数据为该学生生成每日学习计划。

## 归因分析结果
{{ attribution | default('无') }}

## 薄弱点预测
{{ prediction | default('无') }}

## 待复习题目
{{ review_items | default('无') }}

## 间隔复习安排
{{ review_schedule | default('无') }}

## 计划要求
请以JSON格式返回：
1. items: 学习项目数组，每个包含 knowledge_point(知识点)、task_type(任务类型: review/practice/learn)、duration_minutes(建议时长)、priority(高/中/低)、description(任务描述)
2. total_minutes: 总计划时长(整数，分钟)
3. tips: 学习提示数组(字符串，最多3条)

注意：仅返回纯JSON。""",

        'comparison_analysis': """你是一位教育错题分析专家。请基于以下同类错题分组数据进行横向对比分析，找出共性错误模式。

## 同类错题分组数据
{{ groups | default('无数据') }}

## 分析要求
请以JSON格式返回：
1. common_patterns: 共性错误模式数组，每个包含 pattern_name(模式名称)、description(模式描述)、affected_groups(涉及的分组)、frequency(出现频率: 高/中/低)、root_cause(根本原因)
2. suggestions: 改进建议数组，每个包含 target(针对模式)、action(具体行动)、priority(高/中/低)

注意：仅返回纯JSON。""",
    }

    @classmethod
    def _ensure_loaded(cls):
        if not cls._loaded:
            cls._templates.update(cls.BUILTIN_TEMPLATES)
            cls._loaded = True

    @classmethod
    def render(cls, template_key: str, variables: dict = None) -> str:
        cls._ensure_loaded()
        template_str = cls._templates.get(template_key)
        if not template_str:
            raise ValueError(f'Prompt模板不存在: {template_key}')
        template = Template(template_str)
        return template.render(**(variables or {}))

    @classmethod
    def get_available_templates(cls) -> list:
        cls._ensure_loaded()
        return list(cls._templates.keys())
