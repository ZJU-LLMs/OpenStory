from typing import List, Dict, Any, Tuple

from agentkernel_distributed.mas.agent.base.plugin_base import PlanPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from ...utils.schemas import *

logger = get_logger(__name__)

class BasicPlanPlugin(PlanPlugin):
    """
    A basic plan plugin for agents to decide the plan of different granularity.
    """

    # 从地图文件解析的可用地点列表，启动时由 run_simulation.py 注入
    _available_locations: List[str] = []
    # 红楼梦原著角色列表（80回）
    _original_characters: List[str] = [
        "贾宝玉", "林黛玉", "薛宝钗", "王熙凤", "贾母", "王夫人", "贾政",
        "贾探春", "贾迎春", "贾惜春", "李纨", "秦可卿", "妙玉", "史湘云",
        "贾琏", "贾环", "赵姨娘", "平儿", "袭人", "晴雯", "麝月", "紫鹃",
        "莺儿", "香菱", "薛蟠", "薛姨妈", "贾赦", "邢夫人", "尤氏",
        "贾珍", "贾蓉", "贾兰", "刘姥姥", "焦大", "赖大", "林之孝",
        "周瑞", "王善保", "来旺", "智能", "柳五儿", "龄官", "芳官"
    ]

    @classmethod
    def set_locations(cls, locations: List[str]) -> None:
        cls._available_locations = locations
        logger.info(f"【BasicPlanPlugin】已注入 {len(locations)} 个地点: {locations}")

    def __init__(self, redis: RedisKVAdapter) -> None:
        """
        Initialize the Plan Plugin and the variables.
        """
        super().__init__()
        self.redis = redis
        self.model = None
        self.agent_id = None

    async def init(self) -> None:
        """
        Initialize the Plan Plugin, get model and agent_id from component.
        """
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model

        # 在 Actor 内直接解析 TMX，不依赖主进程类变量注入
        if not BasicPlanPlugin._available_locations:
            try:
                import xml.etree.ElementTree as ET
                import os
                tmx_path = os.path.join("map", "sos.tmx")
                tree = ET.parse(tmx_path)
                root = tree.getroot()
                locations = []
                for top_group in root.findall("group"):
                    if top_group.get("name") == "地点":
                        for sub_group in top_group.findall("group"):
                            for layer in sub_group.findall("layer"):
                                name = layer.get("name")
                                if name:
                                    locations.append(name)
                        for layer in top_group.findall("layer"):
                            name = layer.get("name")
                            if name:
                                locations.append(name)
                BasicPlanPlugin._available_locations = locations
                logger.info(f"【{self.agent_id}】【N/A】从 TMX 加载 {len(locations)} 个地点: {locations}")
            except Exception as e:
                logger.warning(f"【{self.agent_id}】【N/A】加载 TMX 地点失败: {e}")

        logger.info(f"【{self.agent_id}】【N/A】BasicPlanPlugin 初始化完成")

    async def _get_all_agent_ids(self) -> List[str]:
        """
        从 Redis 获取所有智能体的 ID 列表

        Returns:
            List[str]: 所有智能体 ID 列表
        """
        agent_ids = []
        try:
            if self.redis and self.redis.client:
                async for key in self.redis.client.scan_iter(match="*:profile"):
                    # key 格式为 "agent_id:profile"，提取 agent_id
                    agent_id = key.split(":")[0]
                    agent_ids.append(agent_id)
        except Exception as e:
            logger.warning(f"【{self.agent_id}】【N/A】获取所有 agent IDs 失败: {e}")
        return agent_ids

    def _format_characters_info(self, all_agent_ids: List[str]) -> str:
        """
        格式化角色信息，区分红楼梦原著角色和新面孔

        Args:
            all_agent_ids: 所有智能体 ID 列表

        Returns:
            str: 格式化的角色信息文本
        """
        # 找出新面孔（不在原著列表中的）
        new_faces = [aid for aid in all_agent_ids if aid not in self._original_characters]

        info_parts = ["世界拥有红楼梦80回时存在的全部角色"]
        if new_faces:
            info_parts.append(f"以及新面孔：{', '.join(new_faces)}")

        return "，".join(info_parts)

    async def execute(self, current_tick: int) -> None:
        """
        Execute the Plan Plugin at every system tick.

        Args:
            current_tick (int): The system current tick.
        """
        try:
            # 通过 agent.get_component() 访问其他组件，然后通过 get_plugin() 获取插件
            state_component = self._component.agent.get_component("state")
            profile_component = self._component.agent.get_component("profile")

            state_plugin = state_component.get_plugin()
            profile_plugin = profile_component.get_plugin()

            # 检查是否活跃
            if not await state_plugin.is_active():
                reason = await state_plugin.get_inactive_reason()
                logger.warning(f"【{self.agent_id}】【{current_tick}】智能体已下线，停止生成计划。原因：{reason}")
                return

            profile = profile_plugin.get_agent_profile()

            # 获取当前的 long_task
            current_long_task = await state_plugin.get_long_task()

            # 如果还没有 long_task，则生成一个
            if current_long_task is None:
                # 生成 long_task
                long_task_str = await self.generate_long_task(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile
                )

                # 将生成的 long_task 存储到 state 中
                await state_plugin.set_long_task(long_task_str)
                current_long_task = long_task_str  # 更新本地变量，供下方时辰计划生成使用
                logger.info(f"【{self.agent_id}】【{current_tick}】已生成并存储 LongTask")
            else:
                logger.debug(f"【{self.agent_id}】【{current_tick}】LongTask 已存在，跳过生成")

            # 在特定 tick（1, 13, 25, 37...）生成12个时辰的计划
            # 规律：从 tick 1 开始，每12个 tick 生成一次
            if current_tick >= 0 and (current_tick) % 12 == 0:
                logger.info(f"【{self.agent_id}】【{current_tick}】开始生成12个时辰计划")

                # 生成12个时辰的计划
                hourly_plans = await self.generate_hourly_plans(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile,
                    long_task=current_long_task
                )

                # 将时辰计划存储到 state 中
                await state_plugin.set_hourly_plans(hourly_plans)
                logger.info(f"【{self.agent_id}】【{current_tick}】已生成并存储12个时辰计划")
            else:
                logger.debug(f"【{self.agent_id}】【{current_tick}】不是计划生成周期，跳过时辰计划生成")

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】执行 PlanPlugin 时出错: {e}")

    async def generate_long_task(self, agent_id: str, current_tick: int, profile: Dict[str, Any]) -> str:
        """
        生成 LongTask 并返回字符串格式

        Args:
            agent_id: 智能体ID
            current_tick: 当前回合数
            profile: 智能体的档案数据

        Returns:
            str: LongTask 的字符串表示
        """
        if not profile:
            logger.warning(f"【{agent_id}】【{current_tick}】未提供人物档案，使用默认配置")
            profile = {}

        # 提取核心驱动
        motivation = profile.get('核心驱动', '未知驱动')

        # 根据人物信息使用大模型生成计划
        plan = await self._generate_plan_based_on_profile(profile)

        # 创建 LongTask 对象
        long_task = LongTask(
            task_description=plan,
            motivation=motivation,
            plan=plan,
            created_tick=current_tick,
            status="pending"
        )

        # 记录生成的 LongTask
        logger.info(f"【{agent_id}】【{current_tick}】生成 LongTask: {long_task.to_string()}")

        # 返回字符串格式
        return long_task.to_string()

    def _format_profile_for_prompt(self, profile: Dict[str, Any]) -> str:
        """
        将 profile 数据格式化为适合大模型的文本格式

        Args:
            profile: 人物档案信息

        Returns:
            str: 格式化后的人物档案文本
        """
        # 提取基本信息
        name = profile.get('id', '未知')
        family = profile.get('家族', '未知')
        gender = profile.get('性别', '未知')

        # 提取核心信息
        personality = profile.get('性格', '未知')
        motivation = profile.get('核心驱动', '未知驱动')
        language_style = profile.get('语言风格', '未知')
        background = profile.get('背景经历', '未知')

        # 提取关系信息
        father = profile.get('父亲', '')
        mother = profile.get('母亲', '')
        status = profile.get('嫡庶', '')

        # 提取重大节点（最近的3个）
        major_events = profile.get('重大节点', [])
        recent_events = major_events[-3:] if len(major_events) > 3 else major_events

        # 构建格式化文本
        formatted_text = f"""人物档案：
姓名：{name}
家族：{family}
性别：{gender}"""

        if father or mother:
            formatted_text += f"\n家庭关系："
            if father:
                formatted_text += f" 父亲-{father}"
            if mother:
                formatted_text += f" 母亲-{mother}"
            if status:
                formatted_text += f" ({status})"

        formatted_text += f"""

性格特点：{personality}
核心驱动：{motivation}
语言风格：{language_style}

背景经历：
{background}"""

        if recent_events:
            formatted_text += f"\n\n重要经历："
            for event in recent_events:
                round_num = event.get('回合', '未知')
                content = event.get('内容', '')
                formatted_text += f"\n- 第{round_num}回合：{content}"

        return formatted_text

    async def _generate_plan_based_on_profile(self, profile: Dict[str, Any]) -> str:
        """
        根据人物档案使用大模型生成具体计划

        Args:
            profile: 人物档案信息

        Returns:
            str: 生成的计划描述
        """
        # 格式化人物档案
        formatted_profile = self._format_profile_for_prompt(profile)

        # 获取所有角色信息
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        # 构建 prompt
        prompt = f"""你是一个智能体的长期计划生成器。请根据以下人物档案信息，生成一个符合人物性格和动机的长期计划。

【重要背景】
- 你当前处于红楼梦第80回
- 请生成符合当前情节背景的计划

【当前世界角色】
{characters_info}

{formatted_profile}

要求：
1. 计划必须紧密结合人物的核心驱动和性格特点
2. 计划应该具体可行，体现人物的行为风格
3. 如果有重要经历，可以考虑这些经历对计划的影响
4. 计划要在有限的时间内可以完成，不要过于长远或短期
5. 计划长度控制在200字之间
6. 明确说明你的任务目标、行动方式以及想要获得的具体结果
7. 【重要】不要使用"因为某某驱动"这类生硬的开头，要以第一人称自然表达
8. 【重要】不要生成规律性的重复行为（如"每天做某事"），而要生成具体的、一次性的目标或事件
9. 计划必须是可实现的，不要设定不切实际的目标

请生成计划："""

        try:
            # 调用大模型生成计划
            if self.model:
                plan = await self.model.chat(prompt)
                plan = plan.strip()
                logger.info(f"【{self.agent_id}】【N/A】使用大模型生成计划: {plan}")
                return plan
            else:
                logger.error(f"【{self.agent_id}】【N/A】模型未初始化，无法生成计划")
                raise Exception("模型未初始化")
        except Exception as e:
            logger.error(f"【{self.agent_id}】【N/A】大模型生成计划失败: {e}")
            raise

    async def generate_hourly_plans(self, agent_id: str, current_tick: int, profile: Dict[str, Any], long_task: str = None) -> List[List[Any]]:
        """
        生成12个时辰的详细计划安排

        Args:
            agent_id: 智能体ID
            current_tick: 当前回合数
            profile: 智能体的档案数据
            long_task: 智能体的长期任务（可选）

        Returns:
            List[List[Any]]: 12个时辰的计划列表，每个元素为 [action, time, target, location, importance]
        """
        if not profile:
            logger.warning(f"【{agent_id}】【{current_tick}】未提供人物档案，使用默认配置")
            profile = {}

        # 格式化人物档案
        formatted_profile = self._format_profile_for_prompt(profile)

        # 获取所有角色信息
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        # 构建 prompt
        long_task_info = f"\n\n【长期目标】\n{long_task}" if long_task else ""

        # 构建地点约束文本
        if self._available_locations:
            locations_str = "、".join(self._available_locations)
            location_rule = f"6. 【严格限制】地点必须从以下列表中选择，不能使用列表外的地点：\n   {locations_str}"
        else:
            location_rule = "6. 地点必须是具体的场所（如：怡红院、潇湘馆、荣庆堂等）"

        prompt = f"""你是一个智能体的时辰计划生成器。请根据以下人物档案信息，生成该人物一天12个时辰的详细行动计划。

【重要背景】
- 你当前处于红楼梦第80回
- 请生成符合当前情节背景的计划

【当前世界角色】
{characters_info}

{formatted_profile}{long_task_info}

古代12时辰对照：
0-子时(23-1点)：休息
1-丑时(1-3点)：深夜
2-寅时(3-5点)：黎明
3-卯时(5-7点)：清晨
4-辰时(7-9点)：早晨
5-巳时(9-11点)：上午
6-午时(11-13点)：中午
7-未时(13-15点)：下午
8-申时(15-17点)：傍晚前
9-酉时(17-19点)：傍晚
10-戌时(19-21点)：晚上
11-亥时(21-23点)：深夜

要求：
1. 为每个时辰(0-11)生成一个具体行动
2. 行动必须符合人物性格、身份和核心驱动
3. 行动要具体，包含动作、目标人物和地点
4. 【重要建议】大部分时间应该专注于自己的事情
   - 一天12个时辰中，建议只有1-2个时辰涉及与其他具体人物的互动（target为具体人名）
   - 其他时辰的target填写"自己"或"无"，表示独自活动
   - 人物大部分时间应该处理自己的日常事务、休息、思考等
5. 【关键】目标人物必须使用全名，不能使用简称：
   - 正确：贾宝玉、林黛玉、薛宝钗、王熙凤、贾母、王夫人、贾政、贾探春
   - 错误：宝玉、黛玉、宝钗、凤姐、探春
   - 如果不涉及具体人物，填写"自己"或"无"
{location_rule}
7. 行动描述控制在10-20字
8. 为每个行动评估重要性分数(1-10)：
   - 1-3分：日常琐事，对剧情影响很小（如：用餐、休息、闲聊）
   - 4-6分：一般活动，有一定剧情价值（如：拜访、交谈、处理事务）
   - 7-8分：重要活动，推动剧情发展（如：关键对话、重要决策、冲突）
   - 9-10分：核心事件，对剧情有重大影响（如：重大转折、关键冲突、命运抉择）
9. 考虑到80回合的总体时间跨度，合理安排行动的节奏和重要性
10. 严格按照JSON格式返回，不要有任何其他文字

请按以下JSON格式返回12个时辰的计划：
[
  {{"action": "行动描述", "time": 0, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  {{"action": "行动描述", "time": 1, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  ...
  {{"action": "行动描述", "time": 11, "target": "目标人物", "location": "地点", "importance": 重要性分数}}
]"""

        try:
            # 调用大模型生成计划
            if not self.model:
                logger.error(f"【{agent_id}】【{current_tick}】模型未初始化，无法生成时辰计划")
                raise Exception("模型未初始化")

            response = await self.model.chat(prompt)
            response = response.strip()

            # 解析JSON响应
            import json
            # 尝试提取JSON部分（如果模型返回了额外的文字）
            start_idx = response.find('[')
            end_idx = response.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                plans_data = json.loads(json_str)
            else:
                plans_data = json.loads(response)

            # 转换为 List[List[Any]] 格式
            hourly_plans = []
            for plan_data in plans_data:
                hourly_plan = HourlyPlan(
                    action=plan_data['action'],
                    time=plan_data['time'],
                    target=plan_data['target'],
                    location=plan_data['location'],
                    importance=plan_data['importance']
                )
                hourly_plans.append(hourly_plan.to_list())

            # 记录涉及其他人物的时辰统计信息
            hourly_plans = self._log_target_statistics(hourly_plans, agent_id, current_tick)

            logger.info(f"【{agent_id}】【{current_tick}】成功生成12个时辰计划")
            return hourly_plans

        except json.JSONDecodeError as e:
            logger.error(f"【{agent_id}】【{current_tick}】解析时辰计划JSON失败: {e}")
            logger.error(f"模型返回内容: {response}")
            raise
        except Exception as e:
            logger.error(f"【{agent_id}】【{current_tick}】生成时辰计划失败: {e}")
            raise

    def _log_target_statistics(self, hourly_plans: List[List[Any]], agent_id: str, current_tick: int) -> List[List[Any]]:
        """
        记录一天内涉及其他人物的时辰统计信息

        Args:
            hourly_plans: 12个时辰的计划列表
            agent_id: 智能体ID
            current_tick: 当前回合数

        Returns:
            List[List[Any]]: 原计划列表（不做修改）
        """
        # 找出所有涉及其他人物的时辰（target不是"自己"或"无"）
        plans_with_target = []
        for i, plan in enumerate(hourly_plans):
            # plan格式: [action, time, target, location, importance]
            target = plan[2]
            if target and target not in ["自己", "无", "None", ""]:
                plans_with_target.append((i, plan))

        # 记录统计信息
        if len(plans_with_target) > 0:
            logger.info(f"【{agent_id}】【{current_tick}】一天内有{len(plans_with_target)}个时辰涉及与其他人物互动")
            for _, plan in plans_with_target:
                logger.debug(f"  - 时辰{plan[1]}: 与 {plan[2]} 互动，重要性{plan[4]}")
        else:
            logger.info(f"【{agent_id}】【{current_tick}】一天内没有与其他人物互动的计划")

        return hourly_plans
