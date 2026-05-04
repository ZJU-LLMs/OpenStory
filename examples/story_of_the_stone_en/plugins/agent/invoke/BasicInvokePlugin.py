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
        """
        try:
            state_component = self._component.agent.get_component("state")
            profile_component = self._component.agent.get_component("profile")

            state_plugin = state_component.get_plugin()
            profile_plugin = profile_component.get_plugin()

            if not await state_plugin.is_active():
                return

            current_day = (current_tick // 12) + 1
            hourly_plans = await state_plugin.get_hourly_plans(day=current_day)
            current_hour = current_tick % 12

            current_plan = None
            if hourly_plans:
                for plan in hourly_plans:
                    if len(plan) >= 5 and plan[1] == current_hour:
                        current_plan = plan
                        break
            else:
                logger.debug(f"[{self.agent_id}][{current_tick}] No hourly plan for day {current_day}")

            user_plan_key = f"user_plan:{self.agent_id}"
            user_plan_data_str = await self.redis.get(user_plan_key)
            if user_plan_data_str:
                try:
                    import json
                    if isinstance(user_plan_data_str, str):
                        user_plan_data = json.loads(user_plan_data_str)
                    else:
                        user_plan_data = user_plan_data_str
                    
                    if user_plan_data.get('tick') == current_tick:
                        logger.info(f"[{self.agent_id}][{current_tick}] Detected highest priority plan set by user!")
                        current_plan = [
                            user_plan_data.get('action', 'Execute user plan'),
                            current_hour,
                            user_plan_data.get('target', 'None'),
                            user_plan_data.get('location', ''),
                            999  
                        ]
                        await self.redis.delete(user_plan_key)
                except Exception as e:
                    logger.warning(f"[{self.agent_id}][{current_tick}] Failed to parse user plan: {e}")

            if not current_plan:
                logger.debug(f"[{self.agent_id}][{current_tick}] No plan for current hour {current_hour}")
                await state_plugin.set_state('current_plan', None)
                await state_plugin.set_state('occupied_by', None)
                await state_plugin.set_state('current_action', None)
                
                idle_desc = f"{self.agent_id} currently has no specific plan and is resting slightly."
                await state_plugin.add_short_term_memory(idle_desc, tick=current_tick)
                return

            await state_plugin.set_state('current_plan', current_plan)

            action = current_plan[0]
            time = current_plan[1]
            target = current_plan[2]
            location = current_plan[3]
            importance = current_plan[4]

            if importance < 7:
                import asyncio
                await asyncio.sleep(5)
                logger.debug(f"[{self.agent_id}][{current_tick}] Low priority task waiting 5 seconds before execution")

            occupation_info = await self._get_occupation(current_tick, self.agent_id)
            if occupation_info:
                occupier = occupation_info.get("occupier")
                occupier_importance = occupation_info.get("importance", 0)
                
                if occupier != self.agent_id and occupier_importance > importance:
                    logger.info(f"[{self.agent_id}][{current_tick}] Occupied by higher priority person {occupier}, skipping original plan")
                    await state_plugin.set_state('occupied_by', occupation_info)
                    
                    occupier_name = occupier.split('.')[-1] 
                    occupier_action = occupation_info.get("action", "some affair")
                    busy_desc = f"Assisting {occupier_name} with {occupier_action}."
                    
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    await state_plugin.set_state('current_action', busy_desc)
                    return
            
            await state_plugin.set_state('occupied_by', None)

            if not await self._occupy(current_tick, importance, action, location):
                occupation_info = await self._get_occupation(current_tick, self.agent_id)
                if occupation_info:
                    occupier_name = occupation_info.get("occupier", "").split('.')[-1]
                    occupier_action = occupation_info.get("action", "some affair")
                    busy_desc = f"Assisting {occupier_name} with {occupier_action}."
                    await state_plugin.set_state('occupied_by', occupation_info)
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    await state_plugin.set_state('current_action', busy_desc)
                return

            logger.info(f"[{self.agent_id}][{current_tick}] Executing plan for hour {time}: {action}")

            self_profile = profile_plugin.get_agent_profile()
            target_profile = None
            plan_note = None  
            target_participated = False  
            if target and target != "None" and target != "自己" and target != "无":
                target_profile = await profile_plugin.get_agent_profile_by_id(target)
                if not target_profile:
                    logger.warning(f"[{self.agent_id}][{current_tick}] Unable to retrieve profile for target {target}")
                else:
                    if not await self._try_occupy_target(current_tick, target, importance, action):
                        plan_note = f"Note: {target} is currently occupied by someone else and cannot cooperate"
                        logger.info(f"[{self.agent_id}][{current_tick}] {plan_note}")
                        await state_plugin.set_state('current_plan_note', plan_note)
                    else:
                        target_participated = True  
                        await state_plugin.set_state('current_plan_note', None)
            else:
                await state_plugin.set_state('current_plan_note', None)

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
                    if dialogue_history:
                        await state_plugin.add_dialogue(current_tick, dialogue_history)
                else:
                    description = description_data
                    dialogue_history = []
            else:
                self_name = self_profile.get('id', 'Unknown')
                description = f"{self_name} is doing {action} at {location}."
                dialogue_history = []
                logger.info(f"[{self.agent_id}][{current_tick}] Generated description using simple template (importance {importance})")

            await state_plugin.add_short_term_memory(description, tick=current_tick)
            await state_plugin.set_state('current_action', description)
            logger.info(f"[{self.agent_id}][{current_tick}] Generated and saved execution description")

            if target_participated:
                try:
                    controller = self._component.agent.controller
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
                    target_plan = [action, time, self.agent_id, location, importance]
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_plan",
                        target_plan
                    )
                    await controller.run_agent_method(
                        target,
                        "state",
                        "add_short_term_memory",
                        description,
                        current_tick
                    )
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_action",
                        description
                    )
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
        try:
            key = f"occupation:{tick}:{self.agent_id}"
            occupation_data = await self.redis.get(key)
            if not occupation_data:
                return False

            occupier = occupation_data.get("occupier")
            occupier_importance = occupation_data.get("importance", 0)

            if occupier == self.agent_id:
                return False

            if occupier_importance > my_importance:
                return True

            return False
        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to check occupation status: {e}")
            return False

    async def _occupy(self, tick: int, importance: int, action: str, location: str = "") -> bool:
        try:
            import json
            key = f"occupation:{tick}:{self.agent_id}"
            existing = await self.redis.get(key)
            if existing:
                if isinstance(existing, str):
                    existing = json.loads(existing)
                occupier = existing.get("occupier")
                occupier_importance = existing.get("importance", 0)
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
        try:
            key = f"occupation:{tick}:{target_id}"
            return await self.redis.get(key)
        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to get occupation info for target {target_id}: {e}")
            return None

    async def _try_occupy_target(self, tick: int, target_id: str, my_importance: int, action: str) -> bool:
        try:
            import json
            occupation_info = await self._get_occupation(tick, target_id)

            if not occupation_info:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.debug(f"[{self.agent_id}][{tick}] Successfully occupied target {target_id} (importance {my_importance}, action: {action})")
                return True

            if isinstance(occupation_info, str):
                occupation_info = json.loads(occupation_info)
            occupier = occupation_info.get("occupier")
            occupier_importance = occupation_info.get("importance", 0)

            if occupier == self.agent_id:
                return True

            if my_importance > occupier_importance:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.info(f"[{self.agent_id}][{tick}] Overwrote occupation of target {target_id} (self {my_importance} > {occupier} {occupier_importance}, action: {action})")
                return True

            logger.info(f"[{self.agent_id}][{tick}] Failed to occupy target {target_id} (self {my_importance} <= {occupier} {occupier_importance})")
            return False

        except Exception as e:
            logger.warning(f"[{self.agent_id}][{tick}] Failed to try occupying target {target_id}: {e}")
            return False

    async def _get_target_importance(self, target_agent_id: str, current_hour: int) -> int:
        try:
            controller = self._component.agent.controller
            target_hourly_plans = await controller.run_agent_method(
                target_agent_id,
                "state",
                "get_hourly_plans"
            )

            if not target_hourly_plans:
                logger.debug(f"[{self.agent_id}] Target {target_agent_id} has no hourly plans")
                return None

            for plan in target_hourly_plans:
                if len(plan) >= 5 and plan[1] == current_hour:
                    return plan[4]  

            logger.debug(f"[{self.agent_id}] Target {target_agent_id} has no plan for hour {current_hour}")
            return None

        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to get importance score for target {target_agent_id}: {e}")
            return None

    async def _get_agent_memory(self, agent_id: str) -> str:
        try:
            controller = self._component.agent.controller
            short_memory = await controller.run_agent_method(agent_id, "state", "get_short_term_memory")
            long_memory = await controller.run_agent_method(agent_id, "state", "get_long_term_memory")
            
            memory_text = ""
            if long_memory:
                memory_text += "[Long-term Memory]\n"
                memory_text += "\n".join([f"- {m['content']}" for m in long_memory]) + "\n\n"
            
            if short_memory:
                memory_text += "[Recent Memory]\n"
                memory_text += "\n".join([f"- {m}" for m in short_memory[-5:]])  
                
            if not memory_text:
                return "No memory"
            return memory_text.strip()
        except Exception as e:
            logger.warning(f"Failed to retrieve memory for {agent_id}: {e}")
            return "No memory"

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
        default_res = {"summary": f"{self_profile.get('id', 'Unknown')} is doing {action} at {location}.", "history": []}
        if not self.model:
            return default_res

        participants = [agent_id]
        absent_people = []  

        if target and target not in ["自己", "无", "None", ""]:
            if plan_note:  
                absent_people.append(target)
            else:
                participants.append(target)

        if len(participants) == 1:
            if absent_people:
                absent_names = ", ".join(absent_people)
                summary = f"{self_profile.get('id', 'Unknown')} is preparing to {action} at {location}, but {absent_names} is busy and didn't come."
                return {"summary": summary, "history": []}
            else:
                return default_res

        try:
            dialogue_history = []
            max_rounds = 10
            current_speaker_idx = 0

            for round_num in range(max_rounds):
                speaker_id = participants[current_speaker_idx]

                if speaker_id == agent_id:
                    speaker_profile = self_profile
                else:
                    speaker_profile = target_profile or {}

                speaker_name = speaker_profile.get('id', speaker_id)
                speaker_memory = await self._get_agent_memory(speaker_id)

                prompt = f"""You are playing the role of {speaker_name}.

Background info:
- Current scene: {action}
- Location: {location}
- Importance: {importance}/10"""

                if absent_people:
                    absent_names = ", ".join(absent_people)
                    prompt += f"\n- Absent: {absent_names} is busy and didn't come."

                if plan_note:
                    prompt += f"\n- Special Note: {plan_note}"

                prompt += f"""

{speaker_name}'s Profile:
- Personality: {speaker_profile.get('性格', 'Unknown')}
- Linguistic Style: {speaker_profile.get('语言风格', 'Unknown')}

{speaker_name}'s Memory & Experience:
{speaker_memory}
"""

                other_participants = [p for p in participants if p != speaker_id]
                if other_participants:
                    prompt += "\nOthers present:"
                    for other_id in other_participants:
                        if other_id == agent_id:
                            other_profile = self_profile
                        else:
                            other_profile = target_profile or {}
                        prompt += f"\n- {other_profile.get('id', other_id)}: {other_profile.get('性格', 'Unknown')}"

                prompt += "\n\nExisting dialogue:\n"
                if dialogue_history:
                    prompt += "\n".join(dialogue_history)
                else:
                    prompt += "(Dialogue just started)"

                prompt += f"""

Please say exactly one line as {speaker_name} (including an action description). Format MUST BE: [Action] Dialogue content
If you think the conversation should end, append the [END] tag at the very end. ALL OUTPUT MUST BE IN ENGLISH.
Example: [Smiles and walks over] "The weather is quite nice today."
Example: [Nods] "Alright, let's leave it at that." [END]

[IMPORTANT FORMAT REQUIREMENT] 
1. DO NOT include the speaker's name in your output (the system will prepend it).
2. Start directly with the [Action] block.

[IMPORTANT] If the current scene involves fatal events (e.g., murder, severe injury, death), it MUST be clearly stated in the action description:
- If someone is killed, write "[Kills XX]" or "[XX dies]"
- If someone is severely injured, write "[XX falls severely injured]"
- Do not be vague; the system relies on this action description to determine character status.

{speaker_name} says:"""

                response = await self.model.chat(prompt)
                response = response.strip()

                # 👇 The hardcoded colon here is critical for the frontend regex to split speaker and dialogue correctly!
                dialogue_line = f"{speaker_name}：{response}"
                dialogue_history.append(dialogue_line)
                logger.info(f"[{current_tick}] Dialogue round {round_num+1}: {dialogue_line}")

                if "[END]" in response or "END" in response:
                    break

                current_speaker_idx = (current_speaker_idx + 1) % len(participants)

            summary_prompt = f"""Here is the dialogue between {', '.join([p for p in participants])} at {location}:

{chr(10).join(dialogue_history)}

Please summarize this interaction in one paragraph (50-100 words), using third-person narrative. Return ONLY the summary text in English, no other words.

[IMPORTANT] If the following fatal events occurred in the dialogue, they MUST be explicitly stated in the summary:
- Death: Must clearly state "XX died" or "XX was killed/beaten to death". No vague terms.
- Severe injury: Must clearly state "XX was severely injured" or "XX is dying".
- Departure: Must clearly state "XX left" or "XX disappeared".
These fatal details are critical for the system to judge character status!"""

            summary = await self.model.chat(summary_prompt)
            summary = summary.strip()
            logger.info(f"[{current_tick}] Dialogue summary: {summary}")
            return {"summary": summary, "history": dialogue_history}

        except Exception as e:
            logger.error(f"[{agent_id}][{current_tick}] Failed to generate dialogue: {e}")
            return default_res

    @property
    def get_last_tick_actions(self) -> List[Dict[str, Any]]:
        pass