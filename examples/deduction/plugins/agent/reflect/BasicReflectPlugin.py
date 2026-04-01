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
            prompt = f"""你是一个智能体的记忆总结助手。请简明扼要地总结以下短期记忆，并提取关键信息。

短期记忆列表：
{memories_text}

要求：
1. 提取最重要的事件和信息
2. 保持时间顺序
3. 去除冗余和不重要的细节
4. 总结长度控制在100-200字之间
5. 只返回总结内容，不要包含任何前缀或解释

请总结："""

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
            prompt = f"""你是一个智能体的任务完成度判定助手。请根据以下信息，判断长期任务（LongTask）是否已经完成。

当前长期任务：
{long_task_str}

所有短期记忆：
{short_context if short_context else "(无)"}

所有长期记忆：
{long_context if long_context else "(无)"}

当前回合(tick)：{current_tick}

要求：
1. 根据长短期记忆中发生的事件，判断该长期任务是否已基本完成
2. 只要任务的核心目标已达成，即使细节不完全一致，也算完成
3. 如果记忆显示任务的主要内容已经执行完毕，请返回"已完成"
4. 只有当任务完全没有进展时，才返回"未完成"
5. 【严格限制】只能返回"已完成"或"未完成"五个字以内，绝不能包含任何其他文字

请判断："""

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
                summary_prompt = f"""你是一个智能体的任务总结助手。请总结以下已完成的长期任务。

已完成的长期任务：
{long_task_str}

相关短期记忆：
{short_context if short_context else "(无)"}

相关长期记忆：
{long_context if long_context else "(无)"}

要求：
1. 简要总结任务的完成情况
2. 提取关键结果和影响
3. 总结长度控制在50-100字之间
4. 只返回总结内容，不要包含任何前缀或解释

请总结："""

                summary = await self.model.chat(summary_prompt)
                summary = summary.strip()

                logger.info(f"[{self.agent_id}][{current_tick}] LongTask summary completed: {summary[:50]}...")

                # Add summary to long-term memory
                await state_plugin.add_long_term_memory(f"[已完成任务] {summary}")

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

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下最近的记忆，判断该角色目前是否处于"无法继续参与后续行动"的状态。

这些状态包括但不限于：
1. 死亡（自杀、被谋杀、病故、被打死、被杀等）
2. 彻底消失/失踪
3. 离家出走/远走高飞/再也不回来
4. 被囚禁/收押
5. 记忆中出现[END]标记，表示角色离场

当前角色：{self.agent_id}

近期记忆：
{memories_text}

【重要判定规则】：
1. 如果记忆中提到"{self.agent_id}死亡"、"{self.agent_id}被打死"、"{self.agent_id}被杀"、"{self.agent_id}去世"等，必须判定为"已离场"
2. 如果记忆中提到某人"杀死了{self.agent_id}"或类似的致命描述，必须判定为"已离场"
3. 如果角色仍然存在、只是暂时休息、或者受伤但未死亡，应判定为"活跃"
4. 只有当记忆中明确发生了上述离场事件时，才判定为"已离场"
5. 严格遵守返回格式：判定结果 | 离场原因（必须包含导致离场的核心因果关系，例如"因为..."）

返回示例：已离场 | 角色因为偷吃仙丹被孙悟空打死
返回示例：已离场 | 角色听到贾宝玉迎娶薛宝钗的消息后悲愤交加而死
返回示例：活跃 |

请分析并返回结果："""

            result = await self.model.chat(prompt)
            result = result.strip()

            if "Active" in result or "活跃" in result:
                return False

            if "Departed" in result or "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "发生了离场事件"
                logger.warning(f"[{self.agent_id}][{current_tick}] {reason}, marked as inactive")
                await state_plugin.set_active_status(False, reason)
                await state_plugin.add_long_term_memory(f"[最终结局] {reason}")

                # Broadcast to other agents
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"[噩耗] {self.agent_id} 已离场。原因：{reason}"
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

            short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories]) if short_memories else "(无)"
            long_context = "\n".join([f"- {m['content']}" for m in long_memories]) if long_memories else "(无)"

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下记忆，判断该角色目前是否处于"无法继续参与后续行动"的状态。

这些状态包括但不限于：
1. 死亡（自杀、被谋杀、病故、被打死、被杀等）
2. 彻底消失/失踪（记忆中没有恢复的迹象）
3. 离家出走/远走高飞（明确表示再也不回来或离开了模拟场景）
4. 被囚禁/收押（长期失去行动自由）

当前角色：{self.agent_id}

近期记忆：
{short_context}

历史长期记忆：
{long_context}

【重要判定规则】：
1. 如果记忆中提到"{self.agent_id}死亡"、"{self.agent_id}被打死"、"{self.agent_id}被杀"、"{self.agent_id}去世"等，必须判定为"已离场"
2. 如果记忆中提到某人"杀死了{self.agent_id}"或类似的致命描述，必须判定为"已离场"
3. 如果角色仍然存在、只是暂时休息、生病但未死亡、或者只是心情低落，应判定为"活跃"
4. 只有当记忆中明确发生了上述离场事件时，才判定为"已离场"
5. 严格遵守返回格式：判定结果 | 离场原因（必须包含导致离场的核心因果关系，例如"因为..."）

返回示例：已离场 | 角色因为偷吃仙丹被孙悟空打死
返回示例：已离场 | 角色听到贾宝玉迎娶薛宝钗的消息后悲愤交加而死
返回示例：活跃 |

请分析并返回结果："""

            if not self.model:
                return False

            result = await self.model.chat(prompt)
            result = result.strip()

            if "Active" in result or "活跃" in result:
                return False
            
            if "Departed" in result or "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "发生了不可逆的离场事件"
                await state_plugin.set_active_status(False, reason)
                
                # Record own final long-term memory
                final_memory = f"[最终结局] {reason}"
                await state_plugin.add_long_term_memory(final_memory)
                
                # Broadcast offline message to all other online agents
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"[噩耗] {self.agent_id} 已离场。原因：{reason}"
                    
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

            short_context = "\n".join([f"- {mem}" for mem in short_memories]) if short_memories else "(无)"
            long_context = "\n".join([f"- {mem['content']}" for mem in long_memories]) if long_memories else "(无)"

            # Build prompt for judgment and adjustment
            prompt = f"""你是一个智能体的战略规划助手。请根据以下记忆和当前情况，判断当前的长期任务（LongTask）是否需要调整。

当前长期任务：
{long_task_str}

近期短期记忆：
{short_context}

历史长期记忆：
{long_context}

当前回合(tick)：{current_tick}

要求：
1. 评估当前任务是否仍然符合当前局势。如果环境发生了重大变化、目标已经偏离、或者出现了更紧急的替代方案，请建议调整。
2. 如果不需要调整，请仅返回"无需调整"。
3. 如果需要调整，请返回调整后的新任务内容。新任务应该清晰、具体，并具有阶段性目标。
4. 只返回结论（"无需调整"或新任务的完整文本），不要包含任何前缀、解释或多余的文字。

请判断并给出结果："""

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
                await state_plugin.add_long_term_memory(f"[任务调整] 由于环境变化，长期任务调整为：{result}")
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask successfully adjusted and recorded")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error adjusting LongTask: {e}")