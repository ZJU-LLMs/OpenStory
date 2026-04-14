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

    # Available locations parsed from map file, injected by run_simulation.py upon startup
    _available_locations: List[str] = []
    # List of original characters from Dream of the Red Chamber (Chapter 80)
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
        logger.info(f"[BasicPlanPlugin] Injected {len(locations)} locations: {locations}")

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

        # Parse TMX directly within Actor, do not rely on main process class variable injection
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
                logger.info(f"[{self.agent_id}][N/A] Loaded {len(locations)} locations from TMX: {locations}")
            except Exception as e:
                logger.warning(f"[{self.agent_id}][N/A] Failed to load TMX locations: {e}")

        logger.info(f"[{self.agent_id}][N/A] BasicPlanPlugin initialization completed")

    async def _get_all_agent_ids(self) -> List[str]:
        """
        Get all agent IDs from Redis

        Returns:
            List[str]: List of all agent IDs
        """
        agent_ids = []
        try:
            if self.redis and self.redis.client:
                async for key in self.redis.client.scan_iter(match="*:profile"):
                    # Key format is "agent_id:profile", extract agent_id
                    agent_id = key.split(":")[0]
                    agent_ids.append(agent_id)
        except Exception as e:
            logger.warning(f"[{self.agent_id}][N/A] Failed to get all agent IDs: {e}")
        return agent_ids

    def _format_characters_info(self, all_agent_ids: List[str]) -> str:
        """
        Format character information, distinguishing original characters and new faces

        Args:
            all_agent_ids: List of all agent IDs

        Returns:
            str: Formatted character information text
        """
        # Find new faces (not in original list)
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
            # Access other components via agent.get_component(), then get plugin via get_plugin()
            state_component = self._component.agent.get_component("state")
            profile_component = self._component.agent.get_component("profile")

            state_plugin = state_component.get_plugin()
            profile_plugin = profile_component.get_plugin()

            # Check if active
            if not await state_plugin.is_active():
                reason = await state_plugin.get_inactive_reason()
                logger.warning(f"[{self.agent_id}][{current_tick}] Agent is offline, stop generating plans. Reason: {reason}")
                return

            profile = profile_plugin.get_agent_profile()

            # Get current long_task
            current_long_task = await state_plugin.get_long_task()

            # If no long_task yet, generate one
            if current_long_task is None:
                # Generate long_task
                long_task_str = await self.generate_long_task(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile
                )

                # Store generated long_task to state
                await state_plugin.set_long_task(long_task_str)
                current_long_task = long_task_str  # Update local variable for hourly plan generation below
                logger.info(f"[{self.agent_id}][{current_tick}] Generated and stored LongTask")
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] LongTask already exists, skipping generation")

            # Generate 12 hourly plans at specific ticks (1, 13, 25, 37...)
            # Pattern: Starting from tick 1, generate once every 12 ticks
            if current_tick >= 0 and (current_tick) % 12 == 0:
                logger.info(f"[{self.agent_id}][{current_tick}] Starting to generate 12 hourly plans")

                # Generate 12 hourly plans
                hourly_plans = await self.generate_hourly_plans(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile,
                    long_task=current_long_task
                )

                # Store hourly plans to state (pass current_tick explicitly to avoid
                # timing issues: state.execute() runs after plan in component_order)
                await state_plugin.set_hourly_plans(hourly_plans, tick=current_tick)
                logger.info(f"[{self.agent_id}][{current_tick}] Generated and stored 12 hourly plans")
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] Not a plan generation cycle, skipping hourly plan generation")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error executing PlanPlugin: {e}")

    async def generate_long_task(self, agent_id: str, current_tick: int, profile: Dict[str, Any]) -> str:
        """
        Generate LongTask and return in string format

        Args:
            agent_id: Agent ID
            current_tick: Current tick number
            profile: Agent profile data

        Returns:
            str: String representation of LongTask
        """
        if not profile:
            logger.warning(f"[{agent_id}][{current_tick}] No profile provided, using default configuration")
            profile = {}

        # Extract core motivation
        motivation = profile.get('核心驱动', '未知驱动')

        # Generate plan using LLM based on character info
        plan = await self._generate_plan_based_on_profile(profile)

        # Create LongTask object
        long_task = LongTask(
            task_description=plan,
            motivation=motivation,
            plan=plan,
            created_tick=current_tick,
            status="pending"
        )

        # Log generated LongTask
        logger.info(f"[{agent_id}][{current_tick}] Generated LongTask: {long_task.to_string()}")

        # Return string format
        return long_task.to_string()

    def _format_profile_for_prompt(self, profile: Dict[str, Any]) -> str:
        """
        Format profile data into text format suitable for LLM

        Args:
            profile: Character profile information

        Returns:
            str: Formatted character profile text
        """
        # Extract basic info
        name = profile.get('id', '未知')
        family = profile.get('家族', '未知')
        gender = profile.get('性别', '未知')

        # Extract core info
        personality = profile.get('性格', '未知')
        motivation = profile.get('核心驱动', '未知驱动')
        language_style = profile.get('语言风格', '未知')
        background = profile.get('背景经历', '未知')

        # Extract relationship info
        father = profile.get('父亲', '')
        mother = profile.get('母亲', '')
        status = profile.get('嫡庶', '')

        # Extract major events (latest 3)
        major_events = profile.get('重大节点', [])
        recent_events = major_events[-3:] if len(major_events) > 3 else major_events

        # Build formatted text
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
        Generate specific plan using LLM based on character profile

        Args:
            profile: Character profile information

        Returns:
            str: Generated plan description
        """
        # Format character profile
        formatted_profile = self._format_profile_for_prompt(profile)

        # Get all characters info
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        # Build prompt
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
10. 必须使用中文输出

请生成计划："""

        try:
            # Call LLM to generate plan
            if self.model:
                plan = await self.model.chat(prompt)
                plan = plan.strip()
                logger.info(f"[{self.agent_id}][N/A] Generated plan using LLM: {plan}")
                return plan
            else:
                logger.error(f"[{self.agent_id}][N/A] Model not initialized, cannot generate plan")
                raise Exception("Model not initialized")
        except Exception as e:
            logger.error(f"[{self.agent_id}][N/A] Failed to generate plan with LLM: {e}")
            raise

    async def generate_hourly_plans(self, agent_id: str, current_tick: int, profile: Dict[str, Any], long_task: str = None) -> List[List[Any]]:
        """
        Generate 12 hourly detailed action plans

        Args:
            agent_id: Agent ID
            current_tick: Current tick number
            profile: Agent profile data
            long_task: Agent long-term task (optional)

        Returns:
            List[List[Any]]: 12 hourly plans list, each element is [action, time, target, location, importance]
        """
        if not profile:
            logger.warning(f"[{agent_id}][{current_tick}] No profile provided, using default configuration")
            profile = {}

        # Format character profile
        formatted_profile = self._format_profile_for_prompt(profile)

        # Get all characters info
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        # Build prompt
        long_task_info = f"\n\n【长期目标】\n{long_task}" if long_task else ""

        # Build location constraint text
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
11. 计划的内容描述必须使用中文输出

请按以下JSON格式返回12个时辰的计划：
[
  {{"action": "行动描述", "time": 0, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  {{"action": "行动描述", "time": 1, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  ...
  {{"action": "行动描述", "time": 11, "target": "目标人物", "location": "地点", "importance": 重要性分数}}
]"""

        try:
            # Call LLM to generate plan
            if not self.model:
                logger.error(f"[{agent_id}][{current_tick}] Model not initialized, cannot generate hourly plans")
                raise Exception("Model not initialized")

            response = await self.model.chat(prompt)
            response = response.strip()

            # Parse JSON response
            import json
            # Try to extract JSON part (in case model returned extra text)
            start_idx = response.find('[')
            end_idx = response.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                plans_data = json.loads(json_str)
            else:
                plans_data = json.loads(response)

            # Convert to List[List[Any]] format
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

            # Log hourly stats involving other characters
            hourly_plans = self._log_target_statistics(hourly_plans, agent_id, current_tick)

            logger.info(f"[{agent_id}][{current_tick}] Successfully generated 12 hourly plans")
            return hourly_plans

        except json.JSONDecodeError as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to parse hourly plan JSON: {e}")
            logger.error(f"Model returned content: {response}")
            raise
        except Exception as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to generate hourly plans: {e}")
            raise

    def _log_target_statistics(self, hourly_plans: List[List[Any]], agent_id: str, current_tick: int) -> List[List[Any]]:
        """
        Log statistics of hours involving other characters within a day

        Args:
            hourly_plans: 12 hourly plans list
            agent_id: Agent ID
            current_tick: Current tick number

        Returns:
            List[List[Any]]: Original plans list (unmodified)
        """
        # Find all hours involving other characters (target is not "self" or "none")
        plans_with_target = []
        for i, plan in enumerate(hourly_plans):
            # plan format: [action, time, target, location, importance]
            target = plan[2]
            if target and target not in ["自己", "无", "None", ""]:
                plans_with_target.append((i, plan))

        # Log statistics
        if len(plans_with_target) > 0:
            logger.info(f"[{agent_id}][{current_tick}] {len(plans_with_target)} hours in a day involve interacting with other characters")
            for _, plan in plans_with_target:
                logger.debug(f"  - Hour {plan[1]}: Interact with {plan[2]}, importance {plan[4]}")
        else:
            logger.info(f"[{agent_id}][{current_tick}] No plans interacting with other characters in a day")

        return hourly_plans

    async def replan_remaining_plans(self, agent_id: str, current_tick: int,
                                     profile: Dict[str, Any], long_task: str = None,
                                     start_hour: int = 0) -> List[List[Any]]:
        """
        Regenerate remaining hourly plans (starting from start_hour)

        Args:
            agent_id: Agent ID
            current_tick: Current tick number
            profile: Agent profile data
            long_task: Agent long-term task
            start_hour: Starting hour (which hour to start generating from)

        Returns:
            List[List[Any]]: Regenerated hourly plans list
        """
        if not profile:
            logger.warning(f"[{agent_id}][{current_tick}] No profile provided, using default configuration")
            profile = {}

        # Format character profile
        formatted_profile = self._format_profile_for_prompt(profile)

        # Get all characters info
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        # Build prompt - only generate remaining hours
        remaining_hours = 12 - start_hour
        long_task_info = f"\n\n【长期目标】\n{long_task}" if long_task else ""

        # Build location constraint text
        if self._available_locations:
            locations_str = "、".join(self._available_locations)
            location_rule = f"6. 【严格限制】地点必须从以下列表中选择，不能使用列表外的地点：\n   {locations_str}"
        else:
            location_rule = "6. 地点必须是具体的场所（如：怡红院、潇湘馆、荣庆堂等）"

        # Build hour mapping
        hour_names = ["子时(23-1点)", "丑时(1-3点)", "寅时(3-5点)", "卯时(5-7点)",
                      "辰时(7-9点)", "巳时(9-11点)", "午时(11-13点)", "未时(13-15点)",
                      "申时(15-17点)", "酉时(17-19点)", "戌时(19-21点)", "亥时(21-23点)"]
        hour_context = "\n".join([f"{i}-{hour_names[i]}" for i in range(start_hour, 12)])

        prompt = f"""你是一个智能体的时辰计划生成器。请根据以下人物档案信息，生成该人物剩余{remaining_hours}个时辰的详细行动计划。

【重要背景】
- 你当前处于红楼梦第80回
- 请生成符合当前情节背景的计划
- 【重要】这是重新规划，只需要为从第{start_hour}个时辰之后的时间生成计划

【当前世界角色】
{characters_info}

{formatted_profile}{long_task_info}

剩余时辰对应：
{hour_context}

要求：
1. 仅为从第{start_hour}个时辰之后的时间生成计划（共{remaining_hours}个时辰）
2. 行动必须符合人物性格、身份和核心驱动
3. 行动要具体，包含动作、目标人物和地点
4. 【重要建议】大部分时间应该专注于自己的事情
   - 建议只有1-2个时辰涉及与其他具体人物的互动
   - 其他时辰的target填写"自己"或"无"
5. 【关键】目标人物必须使用全名，不能使用简称
{location_rule}
7. 行动描述控制在10-20字
8. 为每个行动评估重要性分数(1-10)
9. 严格按照JSON格式返回，不要有任何其他文字
10. 必须使用中文输出

请按以下JSON格式返回{remaining_hours}个时辰的计划：
[
  {{"action": "行动描述", "time": {start_hour}, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  {{"action": "行动描述", "time": {start_hour+1}, "target": "目标人物", "location": "地点", "importance": 重要性分数}},
  ...
  {{"action": "行动描述", "time": 11, "target": "目标人物", "location": "地点", "importance": 重要性分数}}
]"""

        try:
            if not self.model:
                logger.error(f"[{agent_id}][{current_tick}] Model not initialized, cannot replan")
                raise Exception("Model not initialized")

            response = await self.model.chat(prompt)
            response = response.strip()

            # Parse JSON response
            import json
            start_idx = response.find('[')
            end_idx = response.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                plans_data = json.loads(json_str)
            else:
                plans_data = json.loads(response)

            # Merge old and new plans: keep executed, update remaining
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()
            current_day = (current_tick // 12) + 1
            hourly_plans = await state_plugin.get_hourly_plans(day=current_day)

            # Build new plan list
            new_plans = []
            for hour in range(12):
                if hour < start_hour:
                    # Keep executed plans
                    if hourly_plans:
                        for plan in hourly_plans:
                            if len(plan) >= 5 and plan[1] == hour:
                                new_plans.append(plan)
                                break
                    else:
                        # Create empty placeholder if no existing plan
                        new_plans.append(["", hour, "自己", "", 1])
                else:
                    # Add newly generated plans
                    found = False
                    for plan_data in plans_data:
                        if plan_data['time'] == hour:
                            hourly_plan = HourlyPlan(
                                action=plan_data['action'],
                                time=plan_data['time'],
                                target=plan_data['target'],
                                location=plan_data['location'],
                                importance=plan_data['importance']
                            )
                            new_plans.append(hourly_plan.to_list())
                            found = True
                            break
                    if not found:
                        # Create default plan if no corresponding hour plan found
                        new_plans.append(["休息", hour, "自己", "", 1])

            # Save new plans (pass current_tick explicitly for correct day calculation)
            await state_plugin.set_hourly_plans(new_plans, tick=current_tick)
            logger.info(f"[{agent_id}][{current_tick}] Remaining plans replanning completed, total {len(new_plans)} hours")
            return new_plans

        except Exception as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to replan remaining plans: {e}")
            raise
