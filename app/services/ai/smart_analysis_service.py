"""
智能学习分析服务 - 增强版
结合规则分析 + AI深度推理，提供真正的个性化学习分析
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from app import db
from app.models.wrong_question import WrongQuestion
from app.models.question import Question, Chapter, Subject
from app.services.llm import LLMServiceOrchestrator, AllProvidersFailedError

logger = logging.getLogger(__name__)


class SmartAnalysisService:
    """智能学习分析服务"""
    
    @staticmethod
    def analyze_student(user_id: int, use_ai: bool = True) -> dict:
        """
        分析学生学习情况，返回个性化分析报告
        包含：错题统计、薄弱知识点、学习建议、进步趋势
        use_ai: 是否使用AI深度分析
        """
        # 获取错题数据
        wrong_questions = WrongQuestion.query.filter_by(user_id=user_id).all()
        
        if not wrong_questions:
            return {
                'status': 'no_data',
                'message': '暂无错题数据，请先完成一些练习题',
                'analysis': None
            }
        
        # 基础规则分析
        analysis = SmartAnalysisService._analyze_wrong_questions(wrong_questions)
        
        # 生成学习建议
        suggestions = SmartAnalysisService._generate_suggestions(analysis)
        
        # 计算掌握度
        mastery = SmartAnalysisService._calculate_mastery(analysis)
        
        # 预测薄弱点
        weak_points = SmartAnalysisService._predict_weak_points(analysis)
        
        # AI深度分析（可选）
        ai_deep_analysis = None
        if use_ai:
            try:
                ai_deep_analysis = SmartAnalysisService._ai_deep_analysis(
                    user_id, analysis, mastery, weak_points
                )
            except Exception as e:
                logger.warning(f'AI深度分析失败，使用规则分析: {e}')
                ai_deep_analysis = None
        
        return {
            'status': 'success',
            'analysis': {
                'summary': analysis['summary'],
                'mastery': mastery,
                'weak_points': weak_points,
                'suggestions': suggestions,
                'statistics': analysis['statistics'],
                'trend': analysis['trend'],
                'ai_analysis': ai_deep_analysis,
            },
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    def _analyze_wrong_questions(wrong_questions):
        """分析错题数据"""
        records = []
        chapters = defaultdict(lambda: {'total': 0, 'wrong': 0, 'mastered': 0})
        subjects = defaultdict(lambda: {'total': 0, 'wrong': 0})
        difficulties = defaultdict(int)
        reasons = defaultdict(int)
        
        # 按时间分组统计趋势
        now = datetime.now(timezone.utc)
        weekly_stats = defaultdict(lambda: {'wrong': 0, 'mastered': 0})
        
        for wq in wrong_questions:
            question = Question.query.get(wq.question_id)
            if not question:
                continue
            
            chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
            subject = Subject.query.get(question.subject_id) if question.subject_id else None
            
            chapter_name = chapter.name if chapter else '未知'
            subject_name = subject.name if subject else '未知'
            
            # 记录详情
            record = {
                'question_id': wq.question_id,
                'chapter': chapter_name,
                'subject': subject_name,
                'difficulty': question.difficulty,
                'wrong_count': wq.wrong_count,
                'is_mastered': wq.is_mastered,
                'wrong_reason': wq.wrong_reason,
                'created_at': wq.created_at.isoformat() if wq.created_at else None,
            }
            records.append(record)
            
            # 章节统计
            chapters[chapter_name]['total'] += 1
            chapters[chapter_name]['wrong'] += wq.wrong_count
            if wq.is_mastered:
                chapters[chapter_name]['mastered'] += 1
            
            # 学科统计
            subjects[subject_name]['total'] += 1
            subjects[subject_name]['wrong'] += wq.wrong_count
            
            # 难度统计
            difficulties[question.difficulty or '未知'] += 1
            
            # 原因统计
            if wq.wrong_reason:
                reasons[wq.wrong_reason] += 1
            
            # 周统计
            if wq.created_at:
                week_num = wq.created_at.isocalendar()[1]
                weekly_stats[week_num]['wrong'] += 1
                if wq.is_mastered:
                    weekly_stats[week_num]['mastered'] += 1
        
        # 总结
        total_questions = len(records)
        mastered_count = sum(1 for r in records if r['is_mastered'])
        mastery_rate = (mastered_count / total_questions * 100) if total_questions > 0 else 0
        
        summary = {
            'total_wrong_questions': total_questions,
            'mastered_count': mastered_count,
            'not_mastered_count': total_questions - mastered_count,
            'mastery_rate': round(mastery_rate, 1),
            'total_wrong_attempts': sum(r['wrong_count'] for r in records),
        }
        
        # 趋势数据
        trend = {
            'weekly': dict(weekly_stats),
        }
        
        # 统计数据
        statistics = {
            'chapters': dict(chapters),
            'subjects': dict(subjects),
            'difficulties': dict(difficulties),
            'reasons': dict(reasons),
        }
        
        return {
            'summary': summary,
            'statistics': statistics,
            'trend': trend,
            'records': records,
        }
    
    @staticmethod
    def _calculate_mastery(analysis):
        """计算知识点掌握度"""
        chapters = analysis['statistics']['chapters']
        
        mastery = []
        for chapter_name, stats in chapters.items():
            total = stats['total']
            mastered = stats['mastered']
            mastery_rate = (mastered / total * 100) if total > 0 else 0
            
            # 确定掌握水平
            if mastery_rate >= 80:
                level = '优秀'
                color = 'success'
            elif mastery_rate >= 60:
                level = '良好'
                color = 'primary'
            elif mastery_rate >= 40:
                level = '一般'
                color = 'warning'
            else:
                level = '待提高'
                color = 'danger'
            
            mastery.append({
                'name': chapter_name,
                'mastery_rate': round(mastery_rate, 1),
                'level': level,
                'color': color,
                'total_questions': total,
                'mastered_questions': mastered,
            })
        
        # 按掌握度排序
        mastery.sort(key=lambda x: x['mastery_rate'])
        
        return mastery
    
    @staticmethod
    def _predict_weak_points(analysis):
        """预测薄弱知识点"""
        chapters = analysis['statistics']['chapters']
        
        weak_points = []
        for chapter_name, stats in chapters.items():
            total = stats['total']
            mastered = stats['mastered']
            wrong_count = stats['wrong']
            
            # 计算薄弱度（错题多且掌握度低的章节）
            mastery_rate = (mastered / total * 100) if total > 0 else 0
            weak_score = ((100 - mastery_rate) * 0.6) + (min(wrong_count, 20) / 20 * 100 * 0.4)
            
            if weak_score > 40:  # 只显示薄弱度超过40的
                weak_points.append({
                    'name': chapter_name,
                    'weak_score': round(weak_score, 1),
                    'mastery_rate': round(mastery_rate, 1),
                    'wrong_count': wrong_count,
                    'priority': '高' if weak_score > 70 else '中' if weak_score > 50 else '低',
                    'recommendation': SmartAnalysisService._get_chapter_recommendation(chapter_name, mastery_rate, wrong_count)
                })
        
        # 按薄弱度排序
        weak_points.sort(key=lambda x: x['weak_score'], reverse=True)
        
        return weak_points[:10]  # 最多返回10个
    
    @staticmethod
    def _get_chapter_recommendation(chapter_name, mastery_rate, wrong_count):
        """获取章节学习建议"""
        if mastery_rate < 30:
            return f'建议重新学习{chapter_name}的基础知识，重点理解核心概念'
        elif mastery_rate < 60:
            return f'建议针对{chapter_name}进行专项练习，强化薄弱环节'
        elif mastery_rate < 80:
            return f'建议复习{chapter_name}的易错点，提高解题准确率'
        else:
            return f'{chapter_name}掌握良好，可以继续保持'
    
    @staticmethod
    def _generate_suggestions(analysis):
        """生成个性化学习建议"""
        suggestions = []
        
        summary = analysis['summary']
        statistics = analysis['statistics']
        
        # 基于掌握率的建议
        mastery_rate = summary['mastery_rate']
        if mastery_rate < 40:
            suggestions.append({
                'type': 'priority',
                'title': '加强基础练习',
                'content': f'当前错题掌握率仅为{mastery_rate}%，建议先复习基础知识，再做练习题',
                'icon': 'exclamation-triangle',
                'color': 'danger'
            })
        elif mastery_rate < 70:
            suggestions.append({
                'type': 'warning',
                'title': '提高复习效率',
                'content': f'当前错题掌握率为{mastery_rate}%，建议加强错题复习，提高掌握率',
                'icon': 'arrow-up',
                'color': 'warning'
            })
        else:
            suggestions.append({
                'type': 'success',
                'title': '保持良好状态',
                'content': f'当前错题掌握率为{mastery_rate}%，继续保持，争取达到90%以上',
                'icon': 'check-circle',
                'color': 'success'
            })
        
        # 基于错题原因的建议
        reasons = statistics['reasons']
        if reasons:
            top_reason = max(reasons.items(), key=lambda x: x[1])
            suggestions.append({
                'type': 'info',
                'title': '主要错误原因',
                'content': f'你最常犯的错误是"{top_reason[0]}"，共{top_reason[1]}次，建议针对性改进',
                'icon': 'info-circle',
                'color': 'info'
            })
        
        # 基于难度的建议
        difficulties = statistics['difficulties']
        if difficulties.get('困难', 0) > 5:
            suggestions.append({
                'type': 'warning',
                'title': '攻克难题',
                'content': '你有较多困难难度的错题，建议循序渐进，先掌握中等难度题目',
                'icon': 'lightbulb',
                'color': 'warning'
            })
        
        # 学习频率建议
        total_wrong = summary['total_wrong_questions']
        if total_wrong < 10:
            suggestions.append({
                'type': 'info',
                'title': '增加练习量',
                'content': '当前错题数量较少，建议每天完成10-20道练习题',
                'icon': 'book',
                'color': 'info'
            })
        elif total_wrong > 50:
            suggestions.append({
                'type': 'priority',
                'title': '复习优先于新题',
                'content': f'你已有{total_wrong}道错题，建议先复习已掌握的错题，再做新题',
                'icon': 'repeat',
                'color': 'primary'
            })
        
        return suggestions
    
    @staticmethod
    def get_learning_report(user_id: int, report_type='weekly') -> dict:
        """生成学习报告"""
        now = datetime.now(timezone.utc)
        
        if report_type == 'weekly':
            days = 7
            title = '周报'
        else:
            days = 30
            title = '月报'
        
        start_date = now - timedelta(days=days)
        
        # 获取期间错题
        wrong_questions = WrongQuestion.query.filter(
            WrongQuestion.user_id == user_id,
            WrongQuestion.created_at >= start_date
        ).all()
        
        if not wrong_questions:
            return {
                'status': 'no_data',
                'message': f'最近{days}天没有错题记录',
                'report': None
            }
        
        # 统计数据
        total = len(wrong_questions)
        mastered = sum(1 for wq in wrong_questions if wq.is_mastered)
        
        # 按章节统计
        chapters = Counter()
        for wq in wrong_questions:
            question = Question.query.get(wq.question_id)
            if question:
                chapter = Chapter.query.get(question.chapter_id) if question.chapter_id else None
                if chapter:
                    chapters[chapter.name] += 1
        
        # 生成报告
        report = {
            'title': f'学习{title}',
            'period': f'{start_date.strftime("%Y-%m-%d")} 至 {now.strftime("%Y-%m-%d")}',
            'summary': {
                'total_wrong': total,
                'mastered': mastered,
                'mastery_rate': round((mastered / total * 100) if total > 0 else 0, 1),
            },
            'highlights': [],
            'weaknesses': [],
            'recommendations': []
        }
        
        # 亮点
        if mastered > 0:
            report['highlights'].append(f'成功掌握了{mastered}道错题')
        
        if chapters:
            top_chapter = chapters.most_common(1)[0]
            report['weaknesses'].append(f'{top_chapter[0]}章节错题最多（{top_chapter[1]}道）')
        
        # 建议
        mastery_rate = report['summary']['mastery_rate']
        if mastery_rate < 50:
            report['recommendations'].append('建议加强错题复习，提高掌握率')
        if total > 20:
            report['recommendations'].append('错题数量较多，建议控制练习节奏')
        
        return {
            'status': 'success',
            'report': report,
            'generated_at': now.isoformat()
        }
    
    @staticmethod
    def _ai_deep_analysis(user_id, analysis, mastery, weak_points):
        """
        AI深度分析 - 真正的个性化智能分析
        包括：学习风格识别、个性化路径规划、错题根因分析、预测性建议
        """
        # 准备分析数据
        summary = analysis['summary']
        statistics = analysis['statistics']
        reasons = statistics.get('reasons', {})
        chapters = statistics.get('chapters', {})
        
        # 构建分析prompt
        prompt = f"""你是一位专业的教育AI分析师，请基于以下学生数据进行深度个性化分析：

【学生数据概览】
- 总错题数：{summary['total_wrong_questions']}
- 已掌握：{summary['mastered_count']}
- 待掌握：{summary['not_mastered_count']}
- 掌握率：{summary['mastery_rate']}%

【错题原因分布】
{json.dumps(reasons, ensure_ascii=False, indent=2)}

【章节掌握情况】
{json.dumps({k: {'total': v['total'], 'mastered': v['mastered'], 'wrong': v['wrong']} for k, v in list(chapters.items())[:5]}, ensure_ascii=False, indent=2)}

【薄弱知识点】
{json.dumps(weak_points[:3], ensure_ascii=False, indent=2)}

请基于以上数据，用JSON格式返回以下分析结果（必须严格按照格式）：
{{
  "learning_style": "视觉型/听觉型/动手型/综合型",
  "learning_style_analysis": "分析学生的学习风格及依据（100字以内）",
  "cognitive_patterns": ["认知模式1", "认知模式2", "认知模式3"],
  "error_root_causes": [
    {{"chapter": "章节名", "root_cause": "根因分析", "solution": "针对性解决方案"}}
  ],
  "personalized_path": [
    {{"step": 1, "action": "具体行动", "reason": "为什么这样做", "estimated_time": "预估时间"}}
  ],
  "prediction": "基于当前趋势，预测未来2周的学习表现（100字以内）",
  "motivation_tips": ["激励建议1", "激励建议2", "激励建议3"]
}}"""

        try:
            system_prompt = "你是一位专业的教育分析师，擅长学生学习行为分析和个性化学习路径规划。请用中文回复，返回严格的JSON格式。"
            user_prompt = prompt
            
            response = LLMServiceOrchestrator.invoke(
                task_type='smart_analysis',
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
            
            if response and response.success and response.content:
                # 解析AI返回的JSON
                content = response.content.strip()
                if content.startswith('```json'):
                    content = content[7:]
                if content.endswith('```'):
                    content = content[:-3]
                content = content.strip()
                
                try:
                    ai_result = json.loads(content)
                    return ai_result
                except json.JSONDecodeError as e:
                    logger.error(f'AI分析JSON解析失败: {e}, 内容: {content[:200]}')
                    return None
            else:
                logger.warning(f'AI分析调用失败: {response.error_message if response else "无响应"}')
                return None
                
        except Exception as e:
            logger.error(f'AI深度分析异常: {e}', exc_info=True)
            return None
