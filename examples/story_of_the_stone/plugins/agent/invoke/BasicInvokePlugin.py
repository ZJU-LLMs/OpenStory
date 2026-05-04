from typing import List, Dict, Any, TYPE_CHECKING

from agentkernel_distributed.mas.agent.base.plugin_base import InvokePlugin
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.toolkit.storages import RedisKVAdapter
from agentkernel_distributed.types.schemas.action import ActionResult, CallStatus

from ...utils.schemas import *

if TYPE_CHECKING:
    from ..plan.BasicPlanPlugin import BasicPlanPlugin
logger = get_logger(__name__)

class BasicInvokePlugin(InvokePlugin):
    """
    Execute the action from the plan plugin.
    """
    def __init__(self, redis: RedisKVAdapter) -> None:
        super().__init__()
        self.redis = redis
        self.model = None
        self.agent_id = None

    async def init(self) -> None:
        """
        Initialize the Invoke Plugin, get model and agent_id from component.
        """
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        logger.info(f"[{self.agent_id}][N/A] BasicInvokePlugin initialization completed")

    async def execute(self, current_tick: int) -> None:
        """
        Execute the Invoke Plugin at every system tick.

        Args:
            current_tick (int): The system current tick.
        """
        try:
            # Get related components
            state_component = self._component.agent.get_component("state")
            profile_component = self._component.agent.get_component("profile")

            state_plugin = state_component.get_plugin()
            profile_plugin = profile_component.get_plugin()

            # Check if active
            if not await state_plugin.is_active():
                # logger.debug(f"[{self.agent_id}][{current_tick}] Agent is offline, skipping execution")
                return

            # Get current day's plans (every 12 ticks is one day)
            current_day = (current_tick // 12) + 1
            hourly_plans = await state_plugin.get_hourly_plans(day=current_day)

            # Calculate current hour (0-12)
            current_hour = current_tick % 12

            # Find the plan for the current hour
            current_plan = None
            if hourly_plans:
                for plan in hourly_plans:
                    # plan format: [action, time, target, location, importance]
                    if len(plan) >= 5 and plan[1] == current_hour:
                        current_plan = plan
                        break
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] No hourly plan for day {current_day}")

            # Check if there is a highest priority plan set by the user
            user_plan_key = f"user_plan:{self.agent_id}"
            user_plan_data_str = await self.redis.get(user_plan_key)
            if user_plan_data_str:
                try:
                    import json
                    if isinstance(user_plan_data_str, str):
                        user_plan_data = json.loads(user_plan_data_str)
                    else:
                        user_plan_data = user_plan_data_str
                    
                    # Check if the plan is for the current tick
                    if user_plan_data.get('tick') == current_tick:
                        logger.info(f"[{self.agent_id}][{current_tick}] Detected highest priority plan set by user!")
                        current_plan = [
                            user_plan_data.get('action', 'Execute user plan'),
                            current_hour,
                            user_plan_data.get('target', 'None'),
                            user_plan_data.get('location', ''),
                            999  # Highest priority
                        ]
                        # Delete the plan after execution to avoid repetition
                        await self.redis.delete(user_plan_key)
                except Exception as e:
                    logger.warning(f"[{self.agent_id}][{current_tick}] Failed to parse user plan: {e}")

            if not current_plan:
                logger.debug(f"[{self.agent_id}][{current_tick}] No plan for current hour {current_hour}")
                await state_plugin.set_state('current_plan', None)
                await state_plugin.set_state('occupied_by', None)
                await state_plugin.set_state('current_action', None)
                
                # Record a "resting" short-term memory to prevent Tick missing
                idle_desc = f"{self.agent_id}当前没有具体的计划，正在稍作休息。"
                await state_plugin.add_short_term_memory(idle_desc, tick=current_tick)
                return

            # Store the current plan in state for frontend display
            await state_plugin.set_state('current_plan', current_plan)

            # Parse the plan
            action = current_plan[0]
            time = current_plan[1]
            target = current_plan[2]
            location = current_plan[3]
            importance = current_plan[4]

            # If importance is less than 7, wait 5 seconds to let high priority tasks execute first
            if importance < 7:
                import asyncio
                await asyncio.sleep(5)
                logger.debug(f"[{self.agent_id}][{current_tick}] Low priority task waiting 5 seconds before execution")

            # Check if self is occupied
            occupation_info = await self._get_occupation(current_tick, self.agent_id)
            if occupation_info:
                occupier = occupation_info.get("occupier")
                occupier_importance = occupation_info.get("importance", 0)
                
                # If occupied by someone else and their priority is higher
                if occupier != self.agent_id and occupier_importance > importance:
                    logger.info(f"[{self.agent_id}][{current_tick}] Occupied by higher priority person {occupier}, skipping original plan")
                    # Record who occupied and their action in state
                    await state_plugin.set_state('occupied_by', occupation_info)
                    
                    # Record the occupation description
                    occupier_name = occupier.split('.')[-1] # Simple name extraction
                    occupier_action = occupation_info.get("action", "某事")
                    busy_desc = f"正在协助{occupier_name}{occupier_action}。"
                    
                    # First add short-term memory to self, ensuring Tick is not missing
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    # Simultaneously set current_action to occupier's action to ensure frontend shows "current action"
                    await state_plugin.set_state('current_action', busy_desc)
                    return
            
            # If not occupied by others, clear occupation info
            await state_plugin.set_state('occupied_by', None)

            # Occupy self (give up if already preemptively occupied by others)
            if not await self._occupy(current_tick, importance, action, location):
                # Re-read occupation info, go to occupied handling branch
                occupation_info = await self._get_occupation(current_tick, self.agent_id)
                if occupation_info:
                    occupier_name = occupation_info.get("occupier", "").split('.')[-1]
                    occupier_action = occupation_info.get("action", "某事")
                    busy_desc = f"正在协助{occupier_name}{occupier_action}。"
                    await state_plugin.set_state('occupied_by', occupation_info)
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    await state_plugin.set_state('current_action', busy_desc)
                return

            logger.info(f"[{self.agent_id}][{current_tick}] Executing plan for hour {time}: {action}")

            # Get own profile
            self_profile = profile_plugin.get_agent_profile()

            # Get target's profile (if target exists)
            target_profile = None
            plan_note = None  # Plan note
            target_participated = False  # Record if target participated in interaction
            if target and target != "None" and target != "自己" and target != "无":
                target_profile = await profile_plugin.get_agent_profile_by_id(target)
                if not target_profile:
                    logger.warning(f"[{self.agent_id}][{current_tick}] Unable to retrieve profile for target {target}")
                else:
                    # Try to occupy target
                    if not await self._try_occupy_target(current_tick, target, importance, action):
                        plan_note = f"注意：{target}目前正被其他人占用，无法配合"
                        logger.info(f"[{self.agent_id}][{current_tick}] {plan_note}")
                        # Record to state for frontend display
                        await state_plugin.set_state('current_plan_note', plan_note)
                    else:
                        target_participated = True  # Occupation successful, target participated in interaction
                        await state_plugin.set_state('current_plan_note', None)
            else:
                await state_plugin.set_state('current_plan_note', None)

            # Generate execution description (only use LLM for detailed description if importance >= 7)
            if importance >= 7:
                description_data = await self._generate_execution_description(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    action=action,
                    target=target,
                    location=location,
                    importance=importance,
                    self_profile=self_profile,
                    target_profile=target_profile,
                    plan_note=plan_note
                )
                if isinstance(description_data, dict):
                    description = description_data.get("summary", "")
                    dialogue_history = description_data.get("history", [])
                    # Save dialogue history
                    if dialogue_history:
                        await state_plugin.add_dialogue(current_tick, dialogue_history)
                else:
                    description = description_data
                    dialogue_history = []
            else:
                # Use simple template for low importance actions
                self_name = self_profile.get('id', '未知')
                description = f"{self_name}正在{location}执行：{action}。"
                dialogue_history = []
                logger.info(f"[{self.agent_id}][{current_tick}] Generated description using simple template (importance {importance})")

            # Add description to short-term memory (stored by tick, can be overwritten)
            await state_plugin.add_short_term_memory(description, tick=current_tick)
            # Simultaneously store the currently ongoing detailed description into state for frontend "current action" richer display
            await state_plugin.set_state('current_action', description)
            logger.info(f"[{self.agent_id}][{current_tick}] Generated and saved execution description")

            # If target participated in interaction, also add memory to target
            if target_participated:
                try:
                    controller = self._component.agent.controller
                    # Set occupied_by for participant, ensuring frontend can show occupied status
                    occupation_info = {
                        "occupier": self.agent_id,
                        "importance": importance,
                        "action": action
                    }
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "occupied_by",
                        occupation_info
                    )
                    # Set current_plan for participant (including location info), ensuring frontend shows correct location
                    target_plan = [action, time, self.agent_id, location, importance]
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_plan",
                        target_plan
                    )
                    # Add memory to participant
                    await controller.run_agent_method(
                        target,
                        "state",
                        "add_short_term_memory",
                        description,
                        current_tick
                    )
                    # Also set current action description for participant, ensuring frontend can see it
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_action",
                        description
                    )
                    # Also save dialogue history for participant
                    if dialogue_history:
                        await controller.run_agent_method(
                            target,
                            "state",
                            "add_dialogue",
                            current_tick,
                            dialogue_history
                        )
                    logger.info(f"[{self.agent_id}][{current_tick}] Added execution description and dialogue history to participant {target}'s state")
                except Exception as e:
                    logger.warning(f"[{self.agent_id}][{current_tick}] Unable to add state to participant {target}: {e}")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error executing InvokePlugin: {e}")

    async def _is_occupied_by_others(self, tick: int, my_importance: int) -> bool:
        """
        Check if self is occupied by someone else with a higher priority

        Args:
            tick: Current tick
            my_importance: Own importance score

        Returns:
            bool: True if occupied, False otherwise
        """
        try:
            key = f"occupation:{tick}:{self.agent_id}"
            occupation_data = await self.redis.get(key)
            if not occupation_data:
                return False

            occupier = occupation_data.get("occupier")
            occupier_importance = occupation_data.get("importance", 0)

            # If occupier is self, not considered occupied by others
            if occupier == self.agent_id:
                return False

            # If occupier priority is higher, then occupied
            if occupier_importance > my_importance:
                return True

            return False
        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to check occupation status: {e}")
            return False

    async def _occupy(self, tick: int, importance: int, action: str, location: str = "") -> bool:
        """
        Occupy self (only written if not already occupied by others)

        Returns:
            bool: Returns True if successfully occupied, False if already occupied by others
        """
        try:
            import json
            key = f"occupation:{tick}:{self.agent_id}"
            existing = await self.redis.get(key)
            if existing:
                if isinstance(existing, str):
                    existing = json.loads(existing)
                occupier = existing.get("occupier")
                occupier_importance = existing.get("importance", 0)
                # Already occupied by others and their priority is higher, do not overwrite
                if occupier != self.agent_id and occupier_importance > importance:
                    logger.info(f"[{self.agent_id}][{tick}] Self-occupation failed: already occupied by {occupier} (importance {occupier_importance})")
                    return False
            await self.redis.set(key, json.dumps({
                "occupier": self.agent_id,
                "importance": importance,
                "action": action,
                "location": location,
            }))
            logger.debug(f"[{self.agent_id}][{tick}] Self occupied (importance {importance}, action: {action})")
            return True
        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to occupy self: {e}")
            return False

    async def _get_occupation(self, tick: int, target_id: str) -> dict:
        """
        Get occupation info for a target

        Args:
            tick: Current tick
            target_id: Target agent_id

        Returns:
            dict: Occupation info, or None if not occupied
        """
        try:
            key = f"occupation:{tick}:{target_id}"
            return await self.redis.get(key)
        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to get occupation info for target {target_id}: {e}")
            return None

    async def _try_occupy_target(self, tick: int, target_id: str, my_importance: int, action: str) -> bool:
        """
        Try to occupy a target

        Args:
            tick: Current tick
            target_id: Target agent_id
            my_importance: Own importance score
            action: Own action description

        Returns:
            bool: True if successfully occupied, False otherwise
        """
        try:
            import json
            occupation_info = await self._get_occupation(tick, target_id)

            # If target is not occupied, occupy directly
            if not occupation_info:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.debug(f"[{self.agent_id}][{tick}] Successfully occupied target {target_id} (importance {my_importance}, action: {action})")
                return True

            # If already occupied, check priority
            if isinstance(occupation_info, str):
                occupation_info = json.loads(occupation_info)
            occupier = occupation_info.get("occupier")
            occupier_importance = occupation_info.get("importance", 0)

            # If occupier is self, return success
            if occupier == self.agent_id:
                return True

            # If own priority is higher, overwrite occupation
            if my_importance > occupier_importance:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.info(f"[{self.agent_id}][{tick}] Overwrote occupation of target {target_id} (self {my_importance} > {occupier} {occupier_importance}, action: {action})")
                return True

            # Priority not high enough, occupation failed
            logger.info(f"[{self.agent_id}][{tick}] Failed to occupy target {target_id} (self {my_importance} <= {occupier} {occupier_importance})")
            return False

        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to try occupying target {target_id}: {e}")
            return False

    async def _get_target_importance(self, target_agent_id: str, current_hour: int) -> int:
        """
        Get the importance score of the target character's task for the current hour

        Args:
            target_agent_id: Target character ID
            current_hour: Current hour (0-11)

        Returns:
            int: Target character's importance score, or None if unable to retrieve
        """
        try:
            # Get target agent's state component via controller
            controller = self._component.agent.controller
            target_hourly_plans = await controller.run_agent_method(
                target_agent_id,
                "state",
                "get_hourly_plans"
            )

            if not target_hourly_plans:
                logger.debug(f"[{self.agent_id}] Target {target_agent_id} has no hourly plans")
                return None

            # Find target's plan for the current hour
            for plan in target_hourly_plans:
                # plan format: [action, time, target, location, importance]
                if len(plan) >= 5 and plan[1] == current_hour:
                    return plan[4]  # Return importance score

            logger.debug(f"[{self.agent_id}] Target {target_agent_id} has no plan for hour {current_hour}")
            return None

        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to get importance score for target {target_agent_id}: {e}")
            return None

    async def _get_agent_memory(self, agent_id: str) -> str:
        """Get agent's short-term and long-term memory"""
        try:
            controller = self._component.agent.controller
            short_memory = await controller.run_agent_method(agent_id, "state", "get_short_term_memory")
            long_memory = await controller.run_agent_method(agent_id, "state", "get_long_term_memory")
            
            memory_text = ""
            if long_memory:
                memory_text += "[长期记忆]\n"
                memory_text += "\n".join([f"- {m['content']}" for m in long_memory]) + "\n\n"
            
            if short_memory:
                memory_text += "[近期记忆]\n"
                memory_text += "\n".join([f"- {m}" for m in short_memory[-5:]])  # Latest 5 memories
                
            if not memory_text:
                return "无记忆"
            return memory_text.strip()
        except Exception as e:
            logger.warning(f"Failed to retrieve memory for {agent_id}: {e}")
            return "无记忆"

    async def _generate_execution_description(
        self,
        agent_id: str,
        current_tick: int,
        action: str,
        target: str,
        location: str,
        importance: int,
        self_profile: Dict[str, Any],
        target_profile: Dict[str, Any] = None,
        plan_note: str = None
    ) -> Dict[str, Any]:
        """
        Simulate agent dialogue to generate execution description

        Args:
            agent_id: Agent ID
            current_tick: Current tick number
            action: Action description
            target: Target character
            location: Location
            importance: Importance score
            self_profile: Own profile
            target_profile: Target character's profile
            plan_note: Plan note

        Returns:
            Dict[str, Any]: Dictionary containing summary and dialogue history
        """
        default_res = {"summary": f"{self_profile.get('id', '未知')}正在{location}执行：{action}。", "history": []}
        if not self.model:
            return default_res

        # Determine participants
        participants = [agent_id]
        absent_people = []  # Record people who didn't show up because they were busy

        if target and target not in ["自己", "无", "None", ""]:
            if plan_note:  # Target is busy, didn't come
                absent_people.append(target)
            else:
                participants.append(target)

        # Solo action, use simple description
        if len(participants) == 1:
            if absent_people:
                absent_names = "、".join(absent_people)
                summary = f"{self_profile.get('id', '未知')}准备在{location}执行：{action}，但是{absent_names}正忙没来。"
                return {"summary": summary, "history": []}
            else:
                return default_res

        # Multi-person dialogue
        try:
            dialogue_history = []
            max_rounds = 10
            current_speaker_idx = 0

            for round_num in range(max_rounds):
                speaker_id = participants[current_speaker_idx]

                # Get speaker info
                if speaker_id == agent_id:
                    speaker_profile = self_profile
                else:
                    speaker_profile = target_profile or {}

                speaker_name = speaker_profile.get('id', speaker_id)
                speaker_memory = await self._get_agent_memory(speaker_id)

                # Build prompt
                prompt = f"""你正在扮演{speaker_name}。

背景信息：
- 当前场景：{action}
- 地点：{location}
- 重要性：{importance}/10"""

                if absent_people:
                    absent_names = ", ".join(absent_people)
                    prompt += f"\n- 缺席：{absent_names}正忙没来"

                if plan_note:
                    prompt += f"\n- 特殊情况：{plan_note}"

                prompt += f"""

{speaker_name}的档案：
- 性格：{speaker_profile.get('性格', '未知')}
- 语言风格：{speaker_profile.get('语言风格', '未知')}

{speaker_name}的记忆与经历：
{speaker_memory}
"""

                # Add other participants info
                other_participants = [p for p in participants if p != speaker_id]
                if other_participants:
                    prompt += "\n在场的其他人："
                    for other_id in other_participants:
                        if other_id == agent_id:
                            other_profile = self_profile
                        else:
                            other_profile = target_profile or {}
                        prompt += f"\n- {other_profile.get('id', other_id)}：{other_profile.get('性格', '未知')}"

                prompt += "\n\n已有对话：\n"
                if dialogue_history:
                    prompt += "\n".join(dialogue_history)
                else:
                    prompt += "（对话刚开始）"

                prompt += f"""

请以{speaker_name}的身份说一句话（包含动作描述）。格式：[动作]对话内容
如果认为对话应该结束，在最后加上[END]标记。
示例：[微笑着走过来]"你好啊，今天天气不错。"
示例：[点了点头]"好的，那我们就这样吧。"[END]

【重要】如果当前场景涉及致命事件（如杀人、重伤、死亡等），必须在动作描述中明确体现：
- 如果有人被杀死，必须写出"[将XX杀死]"或"[XX死亡]"
- 如果有人重伤，必须写出"[XX重伤倒地]"
- 不要含糊其辞，系统需要根据动作描述判断角色状态

{speaker_name}说：（必须使用中文输出）"""

                response = await self.model.chat(prompt)
                response = response.strip()

                dialogue_line = f"{speaker_name}：{response}"
                dialogue_history.append(dialogue_line)
                logger.info(f"[{current_tick}] Dialogue round {round_num+1}: {dialogue_line}")

                # Check if finished
                if "[END]" in response or "END" in response:
                    break

                # Rotate speaker
                current_speaker_idx = (current_speaker_idx + 1) % len(participants)

            # Generate summary
            summary_prompt = f"""以下是{', '.join([p for p in participants])}在{location}的对话：

{chr(10).join(dialogue_history)}

请用一段话（50-100字）总结这次互动，使用第三人称叙述。只返回总结内容，不要其他文字。

【重要】如果对话中发生了以下致命事件，必须在总结中明确写出：
- 死亡事件：必须写出"XX死亡"或"XX被打死/杀死/身亡"，不能含糊其辞
- 重伤事件：必须写出"XX重伤"或"XX奄奄一息"
- 离场事件：必须写出"XX离开"或"XX消失"
这些致命信息是系统判断角色状态的关键，务必清晰明确！
必须使用中文输出。"""

            summary = await self.model.chat(summary_prompt)
            summary = summary.strip()
            logger.info(f"[{current_tick}] Dialogue summary: {summary}")
            return {"summary": summary, "history": dialogue_history}

        except Exception as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to generate dialogue: {e}")
            return default_res

    @property
    def get_last_tick_actions(self) -> List[Dict[str, Any]]:
        """
        Return the action execution records of the last tick.

        Returns:
            List[Dict[str, Any]]: List of action execution records from the last tick.
        """
        pass
