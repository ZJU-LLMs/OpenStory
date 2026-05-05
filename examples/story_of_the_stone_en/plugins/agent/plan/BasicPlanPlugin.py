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
        """
        # Find new faces (not in original list)
        new_faces = [aid for aid in all_agent_ids if aid not in self._original_characters]

        info_parts = ["The world currently contains all original characters from Chapter 80 of Dream of the Red Chamber"]
        if new_faces:
            info_parts.append(f"as well as new faces: {', '.join(new_faces)}")

        return ", ".join(info_parts)

    async def execute(self, current_tick: int) -> None:
        """
        Execute the Plan Plugin at every system tick.
        """
        try:
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
                long_task_str = await self.generate_long_task(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile
                )
                await state_plugin.set_long_task(long_task_str)
                current_long_task = long_task_str 
                logger.info(f"[{self.agent_id}][{current_tick}] Generated and stored LongTask")
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] LongTask already exists, skipping generation")

            if current_tick >= 0 and (current_tick) % 12 == 0:
                logger.info(f"[{self.agent_id}][{current_tick}] Starting to generate 12 hourly plans")

                hourly_plans = await self.generate_hourly_plans(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile,
                    long_task=current_long_task
                )

                # Pass current_tick explicitly for correct day calculation
                await state_plugin.set_hourly_plans(hourly_plans, tick=current_tick)
                logger.info(f"[{self.agent_id}][{current_tick}] Generated and stored 12 hourly plans")
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] Not a plan generation cycle, skipping hourly plan generation")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error executing PlanPlugin: {e}")

    async def generate_long_task(self, agent_id: str, current_tick: int, profile: Dict[str, Any]) -> str:
        """
        Generate LongTask and return in string format
        """
        if not profile:
            logger.warning(f"[{agent_id}][{current_tick}] No profile provided, using default configuration")
            profile = {}

        motivation = profile.get('核心驱动', 'Unknown drive')
        plan = await self._generate_plan_based_on_profile(profile)

        long_task = LongTask(
            task_description=plan,
            motivation=motivation,
            plan=plan,
            created_tick=current_tick,
            status="pending"
        )
        logger.info(f"[{agent_id}][{current_tick}] Generated LongTask: {long_task.to_string()}")
        return long_task.to_string()

    def _format_profile_for_prompt(self, profile: Dict[str, Any]) -> str:
        """
        Format profile data into text format suitable for LLM in English
        """
        name = profile.get('id', 'Unknown')
        family = profile.get('家族', 'Unknown')
        gender = profile.get('性别', 'Unknown')

        personality = profile.get('性格', 'Unknown')
        motivation = profile.get('核心驱动', 'Unknown drive')
        language_style = profile.get('语言风格', 'Unknown')
        background = profile.get('背景经历', 'Unknown')

        father = profile.get('父亲', '')
        mother = profile.get('母亲', '')
        status = profile.get('嫡庶', '')

        major_events = profile.get('重大节点', [])
        recent_events = major_events[-3:] if len(major_events) > 3 else major_events

        formatted_text = f"""Character Profile:
Name: {name}
Faction: {family}
Gender: {gender}"""

        if father or mother:
            formatted_text += f"\nFamily Relations:"
            if father:
                formatted_text += f" Father-{father}"
            if mother:
                formatted_text += f" Mother-{mother}"
            if status:
                formatted_text += f" ({status})"

        formatted_text += f"""

Personality: {personality}
Core Drive: {motivation}
Linguistic Style: {language_style}

Background:
{background}"""

        if recent_events:
            formatted_text += f"\n\nImportant Experiences:"
            for event in recent_events:
                round_num = event.get('回合', 'Unknown')
                content = event.get('内容', '')
                formatted_text += f"\n- Round {round_num}: {content}"

        return formatted_text

    async def _generate_plan_based_on_profile(self, profile: Dict[str, Any]) -> str:
        """
        Generate specific plan using LLM based on character profile
        """
        formatted_profile = self._format_profile_for_prompt(profile)
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        prompt = f"""You are a long-term plan generator for an AI agent. Based on the following character profile, generate a long-term plan that fits the character's personality and motivation.

[Important Background]
- You are currently in Chapter 80 of Dream of the Red Chamber.
- Please generate a plan fitting the current plot context.

[Current World Characters]
{characters_info}

{formatted_profile}

Requirements:
1. The plan must closely align with the character's core drive and personality.
2. The plan should be specific, feasible, and reflect the character's behavioral style.
3. If there are important past experiences, consider their impact on the plan.
4. The plan should be achievable within a limited time, not too far-fetched or too short-term.
5. Keep the plan description around 200 words. MUST BE IN ENGLISH.
6. Clearly state your task goals, action methods, and specific expected outcomes.
7. [IMPORTANT] Do not use rigid openings like "Because of my drive..."; express it naturally in the first person.
8. [IMPORTANT] Do not generate regular repetitive behaviors (e.g., "Do X every day"); instead, generate specific, one-off goals or events.
9. The plan must be achievable. Do not set unrealistic goals.

Please generate the plan in English:"""

        try:
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
        """
        if not profile:
            logger.warning(f"[{agent_id}][{current_tick}] No profile provided, using default configuration")
            profile = {}

        formatted_profile = self._format_profile_for_prompt(profile)
        all_agent_ids = await self._get_all_agent_ids()
        characters_info = self._format_characters_info(all_agent_ids)

        long_task_info = f"\n\n[Long-term Goal]\n{long_task}" if long_task else ""

        if self._available_locations:
            locations_str = ", ".join(self._available_locations)
            location_rule = f"6. [STRICT RESTRICTION] Location MUST be selected from the following list. DO NOT invent locations:\n   {locations_str}"
        else:
            location_rule = "6. Location must be a specific place (e.g., Yihong Court, Xiaoxiang Lodge, etc.)"

        prompt = f"""You are an hourly plan generator for an AI agent. Based on the character profile, generate a detailed action plan for 12 hours (shichens) of a day.

[Important Background]
- You are currently in Chapter 80 of Dream of the Red Chamber.
- Generate a plan fitting the current plot context.

[Current World Characters]
{characters_info}

{formatted_profile}{long_task_info}

Ancient 12 Shichens mapping:
0-Zi (23-1): Rest
1-Chou (1-3): Late night
2-Yin (3-5): Dawn
3-Mao (5-7): Early morning
4-Chen (7-9): Morning
5-Si (9-11): Late morning
6-Wu (11-13): Noon
7-Wei (13-15): Afternoon
8-Shen (15-17): Late afternoon
9-You (17-19): Dusk
10-Xu (19-21): Evening
11-Hai (21-23): Late night

Requirements:
1. Generate a specific action for each hour (0-11).
2. The actions must match the character's personality, status, and core drive.
3. Actions must be specific, including the action, target person, and location. All output MUST be in English.
4. [IMPORTANT] Most of the time should be focused on their own affairs.
   - Only 1-2 hours a day should involve interacting with other specific characters.
   - For solo hours, fill "target" as "None".
5. [CRITICAL] Target person MUST use their full CHINESE Pinyin name format if they are original characters, or simply their name.
   - Correct: Jia Baoyu, Lin Daiyu, Wang Xifeng
   - Incorrect: Baoyu, Daiyu, Fengjie
   - If no specific person, fill "None"
{location_rule} (Note: you can output Chinese location names for compatibility if required, but try to stick to English descriptions if possible, backend accepts Chinese names for locations).
7. Keep action descriptions between 10-20 words in English.
8. Evaluate the importance score (1-10) for each action:
   - 1-3: Daily routines, minimal plot impact (e.g., dining, resting)
   - 4-6: General activities, some plot value (e.g., visiting, discussing affairs)
   - 7-8: Important activities, drives plot (e.g., key dialogue, important decisions)
   - 9-10: Core events, major plot impact (e.g., major turning point, conflict)
9. Consider the overall time span and arrange action pacing reasonably.
10. Strictly return in JSON format. Do not include any other text.

Please return the 12-hour plan in the following JSON format:
[
  {{"action": "action description in English", "time": 0, "target": "target person", "location": "location name", "importance": score}},
  ...
  {{"action": "action description in English", "time": 11, "target": "target person", "location": "location name", "importance": score}}
]"""

        try:
            if not self.model:
                logger.error(f"[{agent_id}][{current_tick}] Model not initialized, cannot generate hourly plans")
                raise Exception("Model not initialized")

            response = await self.model.chat(prompt)
            response = response.strip()

            import json
            start_idx = response.find('[')
            end_idx = response.rfind(']') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                plans_data = json.loads(json_str)
            else:
                plans_data = json.loads(response)

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
        plans_with_target = []
        for i, plan in enumerate(hourly_plans):
            target = plan[2]
            if target and target not in ["自己", "无", "None", ""]:
                plans_with_target.append((i, plan))

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
        long_task_info = f"\n\n【Long-term Goal】\n{long_task}" if long_task else ""

        # Build location constraint text
        if self._available_locations:
            locations_str = "、".join(self._available_locations)
            location_rule = f"6. 【Strict Limit】Location must be chosen from the following list:\n   {locations_str}"
        else:
            location_rule = "6. Location must be a specific place (e.g., 怡红院, 潇湘馆, 荣庆堂)"

        # Build hour mapping
        hour_names = ["Zi(23-1)", "Chou(1-3)", "Yin(3-5)", "Mao(5-7)",
                      "Chen(7-9)", "Si(9-11)", "Wu(11-13)", "Wei(13-15)",
                      "Shen(15-17)", "You(17-19)", "Xu(19-21)", "Hai(21-23)"]
        hour_context = "\n".join([f"{i}-{hour_names[i]}" for i in range(start_hour, 12)])

        prompt = f"""You are an agent hour plan generator. Based on the following character profile, generate detailed action plans for the remaining {remaining_hours} hours.

【Important Background】
- You are currently at Dream of the Red Chamber Chapter 80
- Please generate plans that fit the current plot context
- 【Important】This is replanning, only need to generate plans for hours after hour {start_hour}

【Current World Characters】
{characters_info}

{formatted_profile}{long_task_info}

Remaining hours:
{hour_context}

Requirements:
1. Only generate plans for hours after hour {start_hour} (total {remaining_hours} hours)
2. Actions must match character personality, status, and core motivation
3. Actions must be specific, including action, target character, and location
4. 【Important Suggestion】Most time should be spent on personal matters
   - Suggest only 1-2 hours involve interaction with specific characters
   - Other hours: target should be "self" or "none"
5. 【Critical】Target character must use full name, not nickname
{location_rule}
7. Action description should be 10-20 characters
8. Evaluate importance score (1-10) for each action
9. Return strictly in JSON format, no other text
10. Must use English for plan content

Return in the following JSON format for {remaining_hours} hours:
[
  {{"action": "action description", "time": {start_hour}, "target": "target character", "location": "location", "importance": score}},
  {{"action": "action description", "time": {start_hour+1}, "target": "target character", "location": "location", "importance": score}},
  ...
  {{"action": "action description", "time": 11, "target": "target character", "location": "location", "importance": score}}
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
                        new_plans.append(["", hour, "self", "", 1])
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
                        new_plans.append(["Rest", hour, "self", "", 1])

            # Save new plans (pass current_tick explicitly for correct day calculation)
            await state_plugin.set_hourly_plans(new_plans, tick=current_tick)
            logger.info(f"[{agent_id}][{current_tick}] Remaining plans replanning completed, total {len(new_plans)} hours")
            return new_plans

        except Exception as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to replan remaining plans: {e}")
            raise