import json
from typing import Dict, Any, Optional, List, Tuple
from agentkernel_distributed.types.schemas.message import Message
from agentkernel_distributed.mas.agent.base.plugin_base import ReflectPlugin
from agentkernel_distributed.toolkit.logger import get_logger
from ...utils.schemas import *

logger = get_logger(__name__)

class BasicReflectPlugin(ReflectPlugin):
    def __init__(self, redis=None) -> None:
        super().__init__()
        self.model = None
        self.agent_id = None
        self.redis = redis  # 用于更新全局分数

    async def init(self) -> None:
        """
        Initialize ReflectPlugin, get model and agent_id
        """
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        # 如果未通过参数注入，尝试从 state 组件的 redis 获取
        if self.redis is None:
            try:
                state_component = self._component.agent.get_component("state")
                state_plugin = state_component.get_plugin()
                self.redis = state_plugin.adapter  # BasicStatePlugin 用 .adapter 不是 .redis
            except Exception as _e:
                logger.warning(f"[{self.agent_id}] Failed to get redis adapter: {_e}")
        logger.info(f"[{self.agent_id}][N/A] BasicReflectPlugin (story) initialized")

    async def execute(self, current_tick: int) -> None:
        """
        Perform a lightweight survival check every tick.
        Full reflection logic (summary, task check, adjustment) every 12 ticks.
        Replan check every tick based on last tick's short-term memory.
        """
        # Perform lightweight survival check every tick (read-only short-term memory)
        if await self._check_life_status_lightweight(current_tick):
            return

        # ===== 剧情模式：每 tick 评估分数贡献 =====
        await self._evaluate_score_contribution(current_tick)

        # Check if replanning is needed based on last tick's memory (every tick)
        # Only check if there are remaining hours (not the last hour of the day)
        current_hour = current_tick % 12
        if current_hour < 11:  # Only replan if there are remaining hours in the day
            should_replan, replan_reason = await self._should_replan(current_tick)
            if should_replan:
                logger.info(f"[{self.agent_id}][{current_tick}] Detected need to replan: {replan_reason}")
                await self._replan_remaining(current_tick, replan_reason)

        # Full reflection logic every 12 ticks
        if (current_tick + 1) % 12 == 0:
            logger.info(f"[{self.agent_id}][{current_tick}] Starting full reflection logic")

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

                logger.info(f"[{self.agent_id}][{current_tick}] Full reflection logic execution completed")
            except Exception as e:
                logger.error(f"[{self.agent_id}][{current_tick}] Error executing full reflection logic: {e}")

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

    async def _evaluate_score_contribution(self, current_tick: int) -> None:
        """
        每 tick 评估该 agent 的行动对复兴大观园稳定度的影响，
        通过 RedisKVAdapter.incr() 原子更新全局 story:score。
        """
        if not self.model or not self.redis:
            return

        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # 读取本 tick 的行动描述
            current_action = await state_plugin.get_state('current_action')
            if not current_action:
                return  # 无行动记录，跳过

            # 若本 agent 是被动参与者（occupied_by 指向另一个 agent），
            # 则该行动的发起方已经评分，跳过，防止重复计分。
            occupied_by = await state_plugin.get_state('occupied_by')
            if occupied_by:
                if isinstance(occupied_by, str):
                    import json as _j
                    try:
                        occupied_by = _j.loads(occupied_by)
                    except Exception:
                        occupied_by = None
                if isinstance(occupied_by, dict):
                    occupier = occupied_by.get('occupier')
                    if occupier and occupier != self.agent_id:
                        logger.debug(f"[{self.agent_id}][{current_tick}] Skipping score eval: passive participant (occupied by {occupier})")
                        return

            prompt = f"""你是大观园复兴稳定度的评判官。请根据以下人物的行动，判断这个行动对复兴大观园的贡献。

复兴大观园目标：修缮大观园建筑、聚拢人心、恢复往日诗意与繁荣。

人物：{self.agent_id}
本轮行动：{current_action}

加分情形（+10分）：
1. 主动修缮或建设大观园的建筑、花园、设施
2. 引入外部资源、资金、物资或有力人脉支持园内复兴
3. 成功化解园内人物之间的重大矛盾或冲突
4. 组织集体活动（诗社、宴会、节庆、雅集等）以提振园内士气
5. 招募、培养或说服有才能的人加入复兴事业

减分情形（-10分）：
1. 在园内挑起或激化重大冲突、斗争
2. 泄露园内机密、背叛同伴或破坏信任关系
3. 大量消耗家族资源而无任何实质收益
4. 故意挑拨家族内部关系导致分裂或离心
5. 主动阻止、破坏他人的复兴行动

中性情形（0分）：
- 日常休息、散步、读书、饮茶等不直接影响复兴的行为

判断要求：
- 若行动明确符合某条加分/减分情形，才返回 +10 或 -10
- 若行动影响较小或无关，返回 0
- 每次只返回一个分值

仅返回以下格式之一（不含任何其他文字）：
+10 | 原因（15字以内）
-10 | 原因（15字以内）
0 | 原因（15字以内）"""

            result = await self.model.chat(prompt)
            result = result.strip()

            # 解析结果
            delta = 0
            reason = ''
            if result.startswith('+10'):
                delta = 10
                parts = result.split('|', 1)
                reason = parts[1].strip() if len(parts) > 1 else '有益于复兴'
            elif result.startswith('-10'):
                delta = -10
                parts = result.split('|', 1)
                reason = parts[1].strip() if len(parts) > 1 else '不利于复兴'
            else:
                return  # 0分不需要更新

            # 原子更新 Redis 分数（RedisKVAdapter.incr 支持负数 amount）
            await self.redis.incr('story:score', amount=delta)

            # 记录事件到 Redis list，供前端展示
            event = json.dumps({
                'tick': current_tick,
                'agent': self.agent_id,
                'delta': delta,
                'reason': f'{self.agent_id}：{reason}'
            }, ensure_ascii=False)
            await self.redis.push('story:score_events', event, left=True)
            if self.redis._client:
                await self.redis._client.ltrim('story:score_events', 0, 99)

            logger.info(f"[{self.agent_id}][{current_tick}] Score delta: {delta:+d} | {reason}")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Score evaluation error: {e}")

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
            prompt = f"""你是一个智能体的记忆总结助手。请简明扼要地总结以下短期记忆并提取关键信息。

短期记忆列表：
{memories_text}

要求：
1. 提取最重要的事件和信息
2. 保持时间顺序
3. 去除冗余和不重要的细节
4. 总结长度保持在100-200字之间
5. 仅返回总结内容，不要包含任何前缀或解释
6. 必须使用中文输出总结

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
            prompt = f"""你是一个智能体的任务完成度判断助手。请根据以下信息判断长期任务（LongTask）是否已经完成。

当前长期任务：
{long_task_str}

所有短期记忆：
{short_context if short_context else "(无)"}

所有长期记忆：
{long_context if long_context else "(无)"}

当前 tick: {current_tick}

要求：
1. 根据短期和长期记忆中的事件判断长期任务是否大致完成
2. 只要任务的核心目标已经达成，即使细节不完全匹配也视为完成
3. 如果记忆显示任务的主要内容已经执行，返回“已完成”
4. 只有在任务完全没有进展时才返回“未完成”
5. 仅返回“已完成”或“未完成”，不要包含任何其他文本

请判断："""

            # Call LLM
            if not self.model:
                logger.error(f"[{self.agent_id}][{current_tick}] Model not initialized, cannot determine LongTask completion")
                return

            completion_status = await self.model.chat(prompt)
            completion_status = completion_status.strip()

            logger.info(f"[{self.agent_id}][{current_tick}] LongTask completion judgment result: {completion_status}")

            # If completed, summarize and clear
            if "已完成" in completion_status or "Completed" in completion_status:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask is completed, starting summary")

                # Build summary prompt
                summary_prompt = f"""你是一个智能体的任务总结助手。请总结以下已完成的长期任务。

已完成的长期任务：
{long_task_str}

相关的短期记忆：
{short_context if short_context else "(无)"}

相关的长期记忆：
{long_context if long_context else "(无)"}

要求：
1. 简要总结任务的完成情况
2. 提取关键结果和影响
3. 总结长度保持在50-100字之间
4. 仅返回总结内容，不要包含任何前缀或解释
5. 必须使用中文输出

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

            # 若已被标记为非活跃，直接返回 True，不再重复扣分
            if not await state_plugin.is_active():
                return True

            short_memories = await state_plugin.get_short_term_memory()
            if not short_memories:
                return False

            # Only take the latest memories for checking
            recent_memories = short_memories[-5:] if len(short_memories) > 5 else short_memories
            memories_text = "\n".join([f"- {m.get('tick', '?')}: {m.get('content', m)}" for m in recent_memories])

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下近期记忆判断角色当前是否处于“无法继续参与后续行动”的状态。

这些状态包括但不限于：
1. 死亡（自杀、被谋杀、病死、被打死、遇害等）
2. 完全消失/失踪
3. 离家出走/远走高飞/再也不回来
4. 被囚禁/拘留
5. 记忆中出现[END]标记，表示角色离场

当前角色：{self.agent_id}

近期记忆：
{memories_text}

[重要判断规则]：
1. 如果记忆中提到“{self.agent_id}死了”、“{self.agent_id}被打死”、“{self.agent_id}遇害”、“{self.agent_id}离世”等，必须判定为“已离场”
2. 如果记忆中提到某人“杀了{self.agent_id}”或类似的致命描述，必须判定为“已离场”
3. 如果角色仍然在场，只是暂时休息，或者受伤但没死，应判定为“活跃”
4. 只有在记忆中明确发生了上述离场事件时，才判定为“已离场”
5. 严格遵循返回格式：判断结果 | 离场原因（必须包含导致离场的核心因果关系，例如“因为...”）
6. 必须使用中文输出

返回示例：已离场 | 角色因为偷吃仙丹被孙悟空打死了
返回示例：已离场 | 角色听闻贾宝玉娶了薛宝钗，悲愤交加而死
返回示例：活跃 |

请分析并返回结果："""

            result = await self.model.chat(prompt)
            result = result.strip()

            if "Active" in result or "活跃" in result:
                return False

            if "Departed" in result or "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "发生不可逆的离场事件"
                logger.warning(f"[{self.agent_id}][{current_tick}] {reason}, marked as inactive")
                await state_plugin.set_active_status(False, reason)
                await state_plugin.add_long_term_memory(f"[最终结局] {reason}")

                # 角色离场：稳定度 -10
                if self.redis:
                    try:
                        await self.redis.incr('story:score', amount=-10)
                        event = json.dumps({
                            'tick': current_tick,
                            'agent': self.agent_id,
                            'delta': -10,
                            'reason': f'{self.agent_id}已离场：{reason[:20]}'
                        }, ensure_ascii=False)
                        await self.redis.push('story:score_events', event, left=True)
                        if self.redis._client:
                            await self.redis._client.ltrim('story:score_events', 0, 99)
                        logger.info(f"[{self.agent_id}][{current_tick}] Departure penalty: -10 (story:score)")
                    except Exception as se:
                        logger.warning(f"[{self.agent_id}] Failed to apply departure penalty: {se}")

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

            short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories]) if short_memories else "(None)"
            long_context = "\n".join([f"- {m['content']}" for m in long_memories]) if long_memories else "(None)"

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下记忆判断角色当前是否处于“无法继续参与后续行动”的状态。

这些状态包括但不限于：
1. 死亡（自杀、被谋杀、病死、被打死、遇害等）
2. 完全消失/失踪（记忆中没有恢复的迹象）
3. 离家出走/远走高飞（明确表示不再回来或离开了模拟场景）
4. 被囚禁/拘留（长期失去行动自由）

当前角色：{self.agent_id}

近期记忆：
{short_context}

历史长期记忆：
{long_context}

[重要判断规则]：
1. 如果记忆中提到“{self.agent_id}死了”、“{self.agent_id}被打死”、“{self.agent_id}遇害”、“{self.agent_id}离世”等，必须判定为“已离场”
2. 如果记忆中提到某人“杀了{self.agent_id}”或类似的致命描述，必须判定为“已离场”
3. 如果角色仍然在场，只是暂时休息，生病但没死，或者只是情绪低落，应判定为“活跃”
4. 只有在记忆中明确发生了上述离场事件时，才判定为“已离场”
5. 严格遵循返回格式：判断结果 | 离场原因（必须包含导致离场的核心因果关系，例如“因为...”）
6. 必须使用中文输出

返回示例：已离场 | 角色因为偷吃仙丹被孙悟空打死了
返回示例：已离场 | 角色听闻贾宝玉娶了薛宝钗，悲愤交加而死
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
                reason = parts[1].strip() if len(parts) > 1 else "发生不可逆的离场事件"
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

            short_context = "\n".join([f"- {mem}" for mem in short_memories]) if short_memories else "(None)"
            long_context = "\n".join([f"- {mem['content']}" for mem in long_memories]) if long_memories else "(None)"

            # Build prompt for judgment and adjustment
            prompt = f"""你是一个智能体的战略规划助手。请根据以下记忆和当前情况，判断当前的长期任务是否需要调整。

当前长期任务：
{long_task_str}

近期短期记忆：
{short_context}

历史长期记忆：
{long_context}

当前 tick: {current_tick}

要求：
1. 评估当前任务是否仍然符合当前情况。如果环境发生了重大变化，目标偏离了，或者出现了更紧急的替代方案，建议进行调整。
2. 如果不需要调整，仅返回“无需调整”。
3. 如果需要调整，返回调整后的新任务内容。新任务应该清晰、具体，并有阶段性目标。
4. 仅返回结论（“无需调整”或新任务的全文），不要包含任何前缀、解释或额外文本。
5. 必须使用中文输出

请判断并给出结果："""

            # Call LLM
            if not self.model:
                logger.error(f"[{self.agent_id}][{current_tick}] Model not initialized, cannot determine LongTask adjustment")
                return

            result = await self.model.chat(prompt)
            result = result.strip()

            if "无需调整" in result or "No Adjustment Needed" in result:
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask is in good shape, no adjustment needed")
            else:
                logger.info(f"[{self.agent_id}][{current_tick}] Detected task needs adjustment.")
                logger.info(f"Old task: {long_task_str}")
                logger.info(f"New task: {result}")
                
                # Directly update state
                await state_plugin.set_long_task(result)
                # Record an adjustment memory
                await state_plugin.add_long_term_memory(f"[任务调整] 由于环境变化，长期任务调整为：{result}")
                # Record adjustment event so frontend can mark future days' plans
                current_day = (current_tick // 12) + 1
                await state_plugin.add_long_task_adjustment(tick=current_tick, from_day=current_day + 1)
                logger.info(f"[{self.agent_id}][{current_tick}] LongTask successfully adjusted and recorded")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error adjusting LongTask: {e}")

    async def _should_replan(self, current_tick: int) -> Tuple[bool, str]:
        """
        Determine if remaining hourly plans need to be replanned

        Returns:
            Tuple[bool, str]: (whether needs replanning, reason)
        """
        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # Get current LongTask
            long_task = await state_plugin.get_long_task()
            if not long_task:
                return (False, "No long-term task")

            # Get short-term memory from last tick
            short_memories = await state_plugin.get_short_term_memory()
            if not short_memories:
                return (False, "No short-term memory")

            last_memory = short_memories[-1]
            last_memory_text = last_memory.get('content', str(last_memory))

            # Get current hour and remaining hours
            current_hour = current_tick % 12
            remaining_hours = 12 - current_hour - 1

            # Get remaining unexecuted hourly plans
            current_day = (current_tick // 12) + 1
            hourly_plans = await state_plugin.get_hourly_plans(day=current_day)

            remaining_plans = []
            if hourly_plans:
                for plan in hourly_plans:
                    if len(plan) >= 5 and plan[1] > current_hour:
                        remaining_plans.append(plan)

            remaining_plans_text = "\n".join([
                f"- Hour {plan[1]}: {plan[0]} (target:{plan[2]}, location:{plan[3]})"
                for plan in remaining_plans
            ]) if remaining_plans else "No remaining plans"

            # Build Prompt
            prompt = f"""你是一个智能体的计划评估助手。请根据近期记忆，判断是否需要重新规划剩余时间。

当前长期任务：{long_task}

上一tick发生的事件：{last_memory_text}

当前时间：第{current_day}天 第{current_hour}个时辰（还剩{remaining_hours}个时辰）

剩余未执行计划：
{remaining_plans_text}

判断标准：
1. 上一tick是否发生了重大变化（如重要角色死亡、任务完成、突发事件）
2. 当前任务是否已经失效或偏离
3. 继续执行原计划是否合理

请返回（仅返回结论）：
- 需要重新规划："需要重新规划 | 原因"
- 无需规划："无需规划 | 原因"
"""

            result = await self.model.chat(prompt)
            result = result.strip()

            logger.info(f"[{self.agent_id}][{current_tick}] Plan replanning decision result: {result}")

            if "需要重新规划" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "Major change occurred"
                return (True, reason)
            else:
                return (False, result)

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error determining replanning: {e}")
            return (False, f"Error: {str(e)}")

    async def _replan_remaining(self, current_tick: int, reason: str) -> None:
        """
        Regenerate remaining hourly plans

        Args:
            current_tick: current tick
            reason: replanning reason
        """
        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            profile_component = self._component.agent.get_component("profile")
            profile_plugin = profile_component.get_plugin()
            profile = profile_plugin.get_agent_profile()

            # Get current LongTask
            long_task = await state_plugin.get_long_task()

            # Calculate current hour and remaining hours
            current_hour = current_tick % 12
            current_day = (current_tick // 12) + 1

            logger.info(f"[{self.agent_id}][{current_tick}] Starting to regenerate remaining plans, current hour {current_hour}, remaining {12-current_hour-1} hours")

            # Call PlanPlugin to regenerate remaining plans
            plan_component = self._component.agent.get_component("plan")
            if plan_component:
                plan_plugin = plan_component.get_plugin()
                # Call the new replan method
                await plan_plugin.replan_remaining_plans(
                    agent_id=self.agent_id,
                    current_tick=current_tick,
                    profile=profile,
                    long_task=long_task,
                    start_hour=current_hour + 1
                )
                logger.info(f"[{self.agent_id}][{current_tick}] Remaining plans replanning completed")
                # Record the replan event so the frontend can highlight changed plan items
                await state_plugin.add_replan_event(
                    tick=current_tick,
                    reason=reason,
                    day=current_day,
                    from_hour=current_hour + 1,
                )
            else:
                logger.warning(f"[{self.agent_id}][{current_tick}] Cannot get plan component")

        except Exception as e:
            logger.error(f"[{self.agent_id}][{current_tick}] Error replanning remaining plans: {e}")
