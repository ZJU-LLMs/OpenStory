from typing import Dict, Any, Optional, List
from agentkernel_distributed.types.schemas.message import Message
from agentkernel_distributed.mas.agent.base.plugin_base import ReflectPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from ...utils.schemas import *

logger = get_logger(__name__)

class BasicReflectPlugin(ReflectPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.model = None
        self.agent_id = None

    async def init(self) -> None:
        """
        Initialize ReflectPlugin, get model and agent_id
        """
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        logger.info(f"[{self.agent_id}][N/A] BasicReflectPlugin initialization completed")

    async def execute(self, current_tick: int) -> None:
        """
        Perform a lightweight survival check every tick, and a full reflection logic every 12 ticks
        """
        # Perform lightweight survival check every tick (read-only short-term memory)
        if await self._check_life_status_lightweight(current_tick):
            return

        # Check if it's a reflection cycle (executed every 12 ticks)
        if (current_tick + 1) % 12 == 0:
            logger.info(f"[{self.agent_id}][{current_tick}] Starting reflection logic")

            try:
                # 1. Summarize short-term memory
                await self._summarize_short_term_memory(current_tick)

                # 2. Check agent survival status (whether dead, disappeared, ran away from home, etc.)
                if await self._check_life_status(current_tick):
                    logger.warning(f"[{self.agent_id}][{current_tick}] Agent is inactive, terminating subsequent reflection logic")
                    return

                # 3. Check LongTask completion status
                await self._check_long_task_completion(current_tick)

                # 4. Dynamically adjust LongTask (if not completed)
                await self._adjust_long_task(current_tick)

                logger.info(f"[{self.agent_id}][{current_tick}] Reflection logic execution completed")
            except Exception as e:
                logger.error(f"[{self.agent_id}][{current_tick}] Error executing reflection logic: {e}")

    async def reflect_task(self, task: LongTask, type: str, current_tick: int = None) -> None:
        """
        Reflect on whether the goal is completed
        """
        pass

    async def reflect_short_memory(self, last_tick_messages: List[Message], last_tick_action: BasicAction, current_tick: int) -> None:
        """
        Short-term memory update
        """
        pass

    async def reflect_long_memory(self, task: LongTask) -> None:
        """
        Long-term memory update
        """
        pass

    async def _summarize_short_term_memory(self, current_tick: int) -> None:
        """
        Summarize short-term memory and store it in long-term memory, then clear short-term memory
        """
        try:
            # Get state component
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # Read all short-term memories
            short_memories = await state_plugin.get_short_term_memory()

            if not short_memories or len(short_memories) == 0:
                logger.info(f"[{self.agent_id}][{current_tick}] Short-term memory is empty, skipping summary")
                return

            logger.info(f"[{self.agent_id}][{current_tick}] Starting to summarize short-term memory, total {len(short_memories)} items")

            # Build prompt for LLM summary
            memories_text = "\n".join([f"{m.get('tick', i)}: {m.get('content', m)}" for i, m in enumerate(short_memories)])
            prompt = f"""You are an agent's memory summary assistant. Please concisely summarize the following short-term memories and extract key information.

Short-term memory list:
{memories_text}

Requirements:
1. Extract the most important events and information
2. Maintain chronological order
3. Remove redundant and unimportant details
4. Keep the summary length between 100-200 words
5. Only return the summary content, do not include any prefixes or explanations

Please summarize:"""

            # Call LLM
            if not self.model:
                logger.error(f"[{self.agent_id}][{current_tick}] Model not initialized, cannot summarize short-term memory")
                return

            summary = await self.model.chat(prompt)
            summary = summary.strip()

            logger.info(f"[{self.agent_id}][{current_tick}] Short-term memory summary completed: {summary[:50]}...")

            # Add summary to long-term memory
            await state_plugin.add_long_term_memory(summary)

            # Clear short-term memory
            await state_plugin.clear_short_term_memory()

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error summarizing short-term memory: {e}")

    async def _check_long_task_completion(self, current_tick: int) -> None:
        """
        Check if LongTask is completed, if so, summarize to long-term memory and clear
        """
        try:
            # Get state and profile components
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            profile_component = self._component.agent.get_component("profile")
            profile_plugin = profile_component.get_plugin()
            profile = profile_plugin.get_agent_profile()

            # Read current LongTask
            long_task_str = await state_plugin.get_long_task()

            if not long_task_str:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask is empty, skipping check")
                return

            logger.info(f"[{self.agent_id}][{current_tick}] Starting to check LongTask completion: {long_task_str[:50]}...")

            # Get all short-term and long-term memories
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            short_context = ""
            if short_memories and len(short_memories) > 0:
                short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories])

            long_context = ""
            if long_memories and len(long_memories) > 0:
                long_context = "\n".join([f"- {mem['content']}" for mem in long_memories])

            # Build prompt for LLM to determine completion
            prompt = f"""You are an agent's task completion judgment assistant. Please judge whether the LongTask has been completed based on the following information.

Current LongTask:
{long_task_str}

All short-term memories:
{short_context if short_context else "(None)"}

All long-term memories:
{long_context if long_context else "(None)"}

Current tick: {current_tick}

Requirements:
1. Judge whether the LongTask is roughly completed based on events in short-term and long-term memory
2. As long as the core goal of the task has been achieved, it is considered completed even if details don't match perfectly
3. If memory shows the main content of the task has been executed, return "Completed"
4. Only return "Not Completed" when there is absolutely no progress on the task
5. Only return "Completed" or "Not Completed", do not include any other text

Please judge:"""

            # Call LLM
            if not self.model:
                logger.error(f"[{self.agent_id}][{current_tick}] Model not initialized, cannot determine LongTask completion")
                return

            completion_status = await self.model.chat(prompt)
            completion_status = completion_status.strip()

            logger.info(f"[{self.agent_id}][{current_tick}] LongTask completion judgment result: {completion_status}")

            # If completed, summarize and clear
            if "Completed" in completion_status or "已完成" in completion_status:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask is completed, starting summary")

                # Build summary prompt
                summary_prompt = f"""You are an agent's task summary assistant. Please summarize the following completed LongTask.

Completed LongTask:
{long_task_str}

Related short-term memories:
{short_context if short_context else "(None)"}

Related long-term memories:
{long_context if long_context else "(None)"}

Requirements:
1. Briefly summarize the completion of the task
2. Extract key outcomes and impacts
3. Keep the summary length between 50-100 words
4. Only return the summary content, do not include any prefixes or explanations

Please summarize:"""

                summary = await self.model.chat(summary_prompt)
                summary = summary.strip()

                logger.info(f"[{self.agent_id}][{current_tick}] LongTask summary completed: {summary[:50]}...")

                # Add summary to long-term memory
                await state_plugin.add_long_term_memory(f"[Completed Task] {summary}")

                # Clear LongTask
                await state_plugin.set_long_task(None)
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask cleared")
            else:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask not completed yet, keeping it")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error checking LongTask completion: {e}")

    async def _check_life_status_lightweight(self, current_tick: int) -> bool:
        """
        Lightweight survival status check, executed every tick.
        Only checks if there is character death/disappearance/departure in short-term memory.
        If detected, immediately marks as inactive.

        Returns:
            bool: Returns True if agent is offline, otherwise False
        """
        if not self.model:
            return False

        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            short_memories = await state_plugin.get_short_term_memory()
            if not short_memories:
                return False

            # Only take the latest memories for checking
            recent_memories = short_memories[-5:] if len(short_memories) > 5 else short_memories
            memories_text = "\n".join([f"- {m.get('tick', '?')}: {m.get('content', m)}" for m in recent_memories])

            prompt = f"""You are an agent survival status analysis assistant. Please determine if the character is currently in a state where they "cannot continue participating in subsequent actions" based on the following recent memories.

These states include but are not limited to:
1. Death (suicide, murdered, died of illness, beaten to death, killed, etc.)
2. Completely disappeared/missing
3. Ran away from home/went far away/never coming back
4. Imprisoned/detained
5. [END] tag appears in memory, indicating character departure

Current character: {self.agent_id}

Recent memories:
{memories_text}

[Important Judgment Rules]:
1. If memory mentions "{self.agent_id} died", "{self.agent_id} was beaten to death", "{self.agent_id} was killed", "{self.agent_id} passed away", etc., must determine as "Departed"
2. If memory mentions someone "killed {self.agent_id}" or similar fatal description, must determine as "Departed"
3. If the character is still present, just resting temporarily, or injured but not dead, should determine as "Active"
4. Only determine as "Departed" when the above departure events clearly occurred in memory
5. Strictly follow the return format: Judgment Result | Departure Reason (must include core cause and effect leading to departure, e.g., "Because...")

Example return: Departed | The character was beaten to death by Sun Wukong because they stole immortal pills
Example return: Departed | The character died of grief and indignation upon hearing Jia Baoyu married Xue Baochai
Example return: Active |

Please analyze and return the result:"""

            result = await self.model.chat(prompt)
            result = result.strip()

            if "Active" in result or "活跃" in result:
                return False

            if "Departed" in result or "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "A departure event occurred"
                logger.warning(f"[{self.agent_id}][{current_tick}] {reason}, marked as inactive")
                await state_plugin.set_active_status(False, reason)
                await state_plugin.add_long_term_memory(f"[Final Ending] {reason}")

                # Broadcast to other agents
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"[Bad News] {self.agent_id} has departed. Reason: {reason}"
                    for target_id in all_agent_ids:
                        if target_id != self.agent_id:
                            await controller.run_agent_method(
                                target_id, "state", "add_long_term_memory", broadcast_msg
                            )
                except Exception as broadcast_err:
                    logger.warning(f"[{self.agent_id}] Failed to broadcast offline message: {broadcast_err}")

                return True

            return False

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error in lightweight survival check: {e}")
            return False

    async def _check_life_status(self, current_tick: int) -> bool:
        """
        Determine if the agent is already dead, disappeared, ran away from home, or imprisoned.
        If in these states, set is_active to False.
        
        Returns:
            bool: Returns True if agent is offline, otherwise False
        """
        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # Get all memories as background
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            # If no memories, default to active
            if not short_memories and not long_memories:
                return False

            short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories]) if short_memories else "(None)"
            long_context = "\n".join([f"- {m['content']}" for m in long_memories]) if long_memories else "(None)"

            prompt = f"""You are an agent survival status analysis assistant. Please determine if the character is currently in a state where they "cannot continue participating in subsequent actions" based on the following memories.

These states include but are not limited to:
1. Death (suicide, murdered, died of illness, beaten to death, killed, etc.)
2. Completely disappeared/missing (with no sign of recovery in memory)
3. Ran away from home/went far away (clearly stated never returning or left simulation scene)
4. Imprisoned/detained (long-term loss of freedom of movement)

Current character: {self.agent_id}

Recent memories:
{short_context}

Historical long-term memories:
{long_context}

[Important Judgment Rules]:
1. If memory mentions "{self.agent_id} died", "{self.agent_id} was beaten to death", "{self.agent_id} was killed", "{self.agent_id} passed away", etc., must determine as "Departed"
2. If memory mentions someone "killed {self.agent_id}" or similar fatal description, must determine as "Departed"
3. If the character is still present, just resting temporarily, sick but not dead, or just depressed, should determine as "Active"
4. Only determine as "Departed" when the above departure events clearly occurred in memory
5. Strictly follow the return format: Judgment Result | Departure Reason (must include core cause and effect leading to departure, e.g., "Because...")

Example return: Departed | The character was beaten to death by Sun Wukong because they stole immortal pills
Example return: Departed | The character died of grief and indignation upon hearing Jia Baoyu married Xue Baochai
Example return: Active |

Please analyze and return the result:"""

            if not self.model:
                return False

            result = await self.model.chat(prompt)
            result = result.strip()

            if "Active" in result or "活跃" in result:
                return False
            
            if "Departed" in result or "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "An irreversible departure event occurred"
                await state_plugin.set_active_status(False, reason)
                
                # Record own final long-term memory
                final_memory = f"[Final Ending] {reason}"
                await state_plugin.add_long_term_memory(final_memory)
                
                # Broadcast offline message to all other online agents
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"[Bad News] {self.agent_id} has departed. Reason: {reason}"
                    
                    for target_id in all_agent_ids:
                        if target_id != self.agent_id:
                            # Send memory to other agents
                            await controller.run_agent_method(
                                target_id,
                                "state",
                                "add_long_term_memory",
                                broadcast_msg
                            )
                    logger.info(f"[{self.agent_id}] Offline message broadcasted to all agents")
                except Exception as broadcast_err:
                    logger.warning(f"[{self.agent_id}] Failed to broadcast offline message: {broadcast_err}")
                
                return True

            return False

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error analyzing survival status: {e}")
            return False

    async def _adjust_long_task(self, current_tick: int) -> None:
        """
        Determine if the current LongTask needs adjustment based on short and long-term memory
        """
        try:
            # Get state component
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # Read current LongTask
            long_task_str = await state_plugin.get_long_task()

            # If task was just cleared (completed), do not adjust
            if not long_task_str:
                return

            logger.info(f"[{self.agent_id}][{current_tick}] Starting to determine if LongTask needs adjustment: {long_task_str[:50]}...")

            # Get all short and long-term memories
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            short_context = "\n".join([f"- {mem}" for mem in short_memories]) if short_memories else "(None)"
            long_context = "\n".join([f"- {mem['content']}" for mem in long_memories]) if long_memories else "(None)"

            # Build prompt for judgment and adjustment
            prompt = f"""You are an agent's strategic planning assistant. Please determine if the current LongTask needs to be adjusted based on the following memories and current situation.

Current LongTask:
{long_task_str}

Recent short-term memories:
{short_context}

Historical long-term memories:
{long_context}

Current tick: {current_tick}

Requirements:
1. Evaluate if the current task still fits the current situation. If the environment has changed significantly, the goal has deviated, or a more urgent alternative has appeared, suggest an adjustment.
2. If no adjustment is needed, only return "No Adjustment Needed".
3. If adjustment is needed, return the adjusted new task content. The new task should be clear, specific, and have phased goals.
4. Only return the conclusion ("No Adjustment Needed" or full text of the new task), do not include any prefixes, explanations, or extra text.

Please judge and give result:"""

            # Call LLM
            if not self.model:
                logger.error(f"[{self.agent_id}][{current_tick}] Model not initialized, cannot determine LongTask adjustment")
                return

            result = await self.model.chat(prompt)
            result = result.strip()

            if "No Adjustment Needed" in result or "无需调整" in result:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask is in good shape, no adjustment needed")
            else:
                logger.info(f"[{self.agent_id}][{current_tick}] Detected task needs adjustment.")
                logger.info(f"Old task: {long_task_str}")
                logger.info(f"New task: {result}")
                
                # Directly update state
                await state_plugin.set_long_task(result)
                # Record an adjustment memory
                await state_plugin.add_long_term_memory(f"[Task Adjustment] Due to environmental changes, LongTask adjusted to: {result}")
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask successfully adjusted and recorded")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error adjusting LongTask: {e}")
