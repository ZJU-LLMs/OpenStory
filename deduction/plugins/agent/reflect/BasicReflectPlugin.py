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
        初始化 ReflectPlugin，获取 model 和 agent_id
        """
        self.agent_id = self._component.agent.agent_id
        self.model = self._component.agent.model
        logger.info(f"【{self.agent_id}】【N/A】BasicReflectPlugin 初始化完成")

    async def execute(self, current_tick: int) -> None:
        """
        每个 tick 执行轻量级生存检查，每12个tick执行完整反思逻辑
        """
        # 每个 tick 都执行轻量级生存检查（只读短期记忆）
        if await self._check_life_status_lightweight(current_tick):
            return

        # 判断是否是反思周期（每12个tick执行一次）
        if (current_tick + 1) % 12 == 0:
            logger.info(f"【{self.agent_id}】【{current_tick}】开始执行反思逻辑")

            try:
                # 1. 总结短期记忆
                await self._summarize_short_term_memory(current_tick)

                # 2. 判断智能体生存状态（是否死亡、消失、离家出走等）
                if await self._check_life_status(current_tick):
                    logger.warning(f"【{self.agent_id}】【{current_tick}】智能体已处于非活跃状态，终止后续反思逻辑")
                    return

                # 3. 检查LongTask完成情况
                await self._check_long_task_completion(current_tick)

                # 4. 动态调整LongTask（如果尚未完成）
                await self._adjust_long_task(current_tick)

                logger.info(f"【{self.agent_id}】【{current_tick}】反思逻辑执行完成")
            except Exception as e:
                logger.error(f"【{self.agent_id}】【{current_tick}】执行反思逻辑时出错: {e}")

    async def reflect_task(self, task: LongTask, type: str, current_tick: int = None) -> None:
        """
        反思目标是否完成
        """
        pass

    async def reflect_short_memory(self, last_tick_messages: List[Message], last_tick_action: BasicAction, current_tick: int) -> None:
        """
        短期记忆更新
        """
        pass

    async def reflect_long_memory(self, task: LongTask) -> None:
        """
        长期记忆更新
        """
        pass

    async def _summarize_short_term_memory(self, current_tick: int) -> None:
        """
        总结短期记忆并存入长期记忆，然后清空短期记忆
        """
        try:
            # 获取state组件
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # 读取所有短期记忆
            short_memories = await state_plugin.get_short_term_memory()

            if not short_memories or len(short_memories) == 0:
                logger.info(f"【{self.agent_id}】【{current_tick}】短期记忆为空，跳过总结")
                return

            logger.info(f"【{self.agent_id}】【{current_tick}】开始总结短期记忆，共{len(short_memories)}条")

            # 构建prompt让大模型总结
            memories_text = "\n".join([f"{m.get('tick', i)}: {m.get('content', m)}" for i, m in enumerate(short_memories)])
            prompt = f"""你是一个智能体的记忆总结助手。请将以下短期记忆进行精简总结，提取关键信息。

短期记忆列表：
{memories_text}

要求：
1. 提取最重要的事件和信息
2. 保持时间顺序
3. 去除冗余和不重要的细节
4. 总结长度控制在100-200字
5. 只返回总结内容，不要包含任何前缀或解释

请总结："""

            # 调用大模型
            if not self.model:
                logger.error(f"【{self.agent_id}】【{current_tick}】模型未初始化，无法总结短期记忆")
                return

            summary = await self.model.chat(prompt)
            summary = summary.strip()

            logger.info(f"【{self.agent_id}】【{current_tick}】短期记忆总结完成: {summary[:50]}...")

            # 将总结添加到长期记忆
            await state_plugin.add_long_term_memory(summary)

            # 清空短期记忆
            await state_plugin.clear_short_term_memory()

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】总结短期记忆时出错: {e}")

    async def _check_long_task_completion(self, current_tick: int) -> None:
        """
        检查LongTask是否完成，如果完成则总结到长期记忆并清空
        """
        try:
            # 获取state和profile组件
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            profile_component = self._component.agent.get_component("profile")
            profile_plugin = profile_component.get_plugin()
            profile = profile_plugin.get_agent_profile()

            # 读取当前LongTask
            long_task_str = await state_plugin.get_long_task()

            if not long_task_str:
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask为空，跳过检查")
                return

            logger.info(f"【{self.agent_id}】【{current_tick}】开始检查LongTask完成情况: {long_task_str[:50]}...")

            # 获取所有短期记忆和长期记忆
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            short_context = ""
            if short_memories and len(short_memories) > 0:
                short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories])

            long_context = ""
            if long_memories and len(long_memories) > 0:
                long_context = "\n".join([f"- {mem['content']}" for mem in long_memories])

            # 构建prompt让大模型判断是否完成
            prompt = f"""你是一个智能体的任务完成判断助手。请根据以下信息判断LongTask是否已经完成。

当前LongTask：
{long_task_str}

所有短期记忆：
{short_context if short_context else "（暂无）"}

所有长期记忆：
{long_context if long_context else "（暂无）"}

当前回合数：{current_tick}

要求：
1. 根据短期记忆和长期记忆中的事件，判断LongTask是否大致完成
2. 只要任务的核心目标已经达成，即使细节不完全匹配也算完成
3. 如果记忆中显示任务的主要内容已执行，返回"已完成"
4. 只有任务完全没有进展时才返回"未完成"
5. 只返回"已完成"或"未完成"，不要包含任何其他文字

请判断："""

            # 调用大模型
            if not self.model:
                logger.error(f"【{self.agent_id}】【{current_tick}】模型未初始化，无法判断LongTask完成情况")
                return

            completion_status = await self.model.chat(prompt)
            completion_status = completion_status.strip()

            logger.info(f"【{self.agent_id}】【{current_tick}】LongTask完成判断结果: {completion_status}")

            # 如果已完成，总结并清空
            if "已完成" in completion_status:
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask已完成，开始总结")

                # 构建总结prompt
                summary_prompt = f"""你是一个智能体的任务总结助手。请总结以下已完成的LongTask。

已完成的LongTask：
{long_task_str}

相关短期记忆：
{short_context if short_context else "（暂无）"}

相关长期记忆：
{long_context if long_context else "（暂无）"}

要求：
1. 简要总结任务的完成情况
2. 提取关键成果和影响
3. 总结长度控制在50-100字
4. 只返回总结内容，不要包含任何前缀或解释

请总结："""

                summary = await self.model.chat(summary_prompt)
                summary = summary.strip()

                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask总结完成: {summary[:50]}...")

                # 将总结添加到长期记忆
                await state_plugin.add_long_term_memory(f"【已完成任务】{summary}")

                # 清空LongTask
                await state_plugin.set_long_task(None)
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask已清空")
            else:
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask尚未完成，继续保留")

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】检查LongTask完成情况时出错: {e}")

    async def _check_life_status_lightweight(self, current_tick: int) -> bool:
        """
        轻量级生存状态检查，每个 tick 都执行。
        只检查短期记忆中是否有角色死亡/消失/离场。
        如果检测到，立即标记为非活跃。

        Returns:
            bool: 如果智能体已下线返回 True，否则返回 False
        """
        if not self.model:
            return False

        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            short_memories = await state_plugin.get_short_term_memory()
            if not short_memories:
                return False

            # 只取最新的记忆进行检查
            recent_memories = short_memories[-5:] if len(short_memories) > 5 else short_memories
            memories_text = "\n".join([f"- {m.get('tick', '?')}: {m.get('content', m)}" for m in recent_memories])

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下近期记忆，判断该角色当前是否已经处于”无法继续参与后续行动”的状态。

这些状态包括但不限于：
1. 死亡（自尽、被害、病故、被打死、被杀死、身亡、殒命等）
2. 彻底消失/失踪
3. 离家出走/远走他乡/再也不回来
4. 坐牢/羁押
5. 记忆中出现[END]标记，表示角色离场

当前角色：{self.agent_id}

近期记忆：
{memories_text}

【重要判断规则】：
1. 如果记忆中提到”{self.agent_id}死亡”、”{self.agent_id}被打死”、”{self.agent_id}被杀死”、”{self.agent_id}身亡”等，必须判定为”已离场”
2. 如果记忆中提到有人”将{self.agent_id}杀死”或类似致命描述，必须判定为”已离场”
3. 如果角色仍然在场、只是暂时休息或受伤但未死，应判定为”活跃”
4. 只有当记忆中明确发生了上述离场事件时，才判定为”已离场”
5. 严格按照格式返回：判定结果 | 离场原因（必须包含导致离场的核心前因后果，例如“因为...所以...”）

示例返回：已离场 | 角色因为偷吃仙丹被孙悟空一棒打死
示例返回：已离场 | 角色因为听闻贾宝玉娶了薛宝钗，悲愤交加气绝身亡
示例返回：活跃 |

请分析并返回结果："""

            result = await self.model.chat(prompt)
            result = result.strip()

            if "活跃" in result:
                return False

            if "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "发生了离场事件"
                logger.warning(f"【{self.agent_id}】【{current_tick}】{reason}，标记为非活跃")
                await state_plugin.set_active_status(False, reason)
                await state_plugin.add_long_term_memory(f"【最终结局】{reason}")

                # 广播给其他智能体
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"【闻听噩耗】{self.agent_id} 已离场。原因：{reason}"
                    for target_id in all_agent_ids:
                        if target_id != self.agent_id:
                            await controller.run_agent_method(
                                target_id, "state", "add_long_term_memory", broadcast_msg
                            )
                except Exception as broadcast_err:
                    logger.warning(f"【{self.agent_id}】下线消息广播失败: {broadcast_err}")

                return True

            return False

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】轻量级生存检查出错: {e}")
            return False

    async def _check_life_status(self, current_tick: int) -> bool:
        """
        判断智能体是否已经死亡、消失、离家出走或坐牢。
        如果处于这些状态，设置 is_active 为 False。
        
        Returns:
            bool: 如果智能体已下线返回 True，否则返回 False
        """
        try:
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # 获取所有记忆作为背景
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            # 如果没有任何记忆，默认活跃
            if not short_memories and not long_memories:
                return False

            short_context = "\n".join([f"- {m.get('content', m)}" for m in short_memories]) if short_memories else "（暂无）"
            long_context = "\n".join([f"- {m['content']}" for m in long_memories]) if long_memories else "（暂无）"

            prompt = f"""你是一个智能体生存状态分析助手。请根据以下记忆，判断该角色当前是否已经处于”无法继续参与后续行动”的状态。

这些状态包括但不限于：
1. 死亡（自尽、被害、病故、被打死、被杀死、身亡、殒命等）
2. 彻底消失/失踪（且记忆中没有找回的迹象）
3. 离家出走/远走他乡（明确表示永不回来或已离开模拟场景）
4. 坐牢/羁押（长期失去行动自由）

当前角色：{self.agent_id}

近期记忆：
{short_context}

历史长期记忆：
{long_context}

【重要判断规则】：
1. 如果记忆中提到”{self.agent_id}死亡”、”{self.agent_id}被打死”、”{self.agent_id}被杀死”、”{self.agent_id}身亡”等，必须判定为”已离场”
2. 如果记忆中提到有人”将{self.agent_id}杀死”或类似致命描述，必须判定为”已离场”
3. 如果角色仍然在场、只是暂时休息、生病但未死、或者仅仅是情绪低落，应判定为”活跃”
4. 只有当记忆中明确发生了上述离场事件时，才判定为”已离场”
5. 严格按照格式返回：判定结果 | 离场原因（必须包含导致离场的核心前因后果，例如“因为...所以...”）

示例返回：已离场 | 角色因为偷吃仙丹被孙悟空一棒打死
示例返回：已离场 | 角色因为听闻贾宝玉娶了薛宝钗，悲愤交加气绝身亡
示例返回：活跃 |

请分析并返回结果："""

            if not self.model:
                return False

            result = await self.model.chat(prompt)
            result = result.strip()

            if "活跃" in result:
                return False
            
            if "已离场" in result:
                parts = result.split('|')
                reason = parts[1].strip() if len(parts) > 1 else "发生了不可逆的离场事件"
                await state_plugin.set_active_status(False, reason)
                
                # 记录自己的最后一条长期记忆
                final_memory = f"【最终结局】{reason}"
                await state_plugin.add_long_term_memory(final_memory)
                
                # 将下线消息广播给所有其他在线智能体
                try:
                    controller = self._component.agent.controller
                    all_agent_ids = await controller.get_all_agent_ids()
                    broadcast_msg = f"【闻听噩耗】{self.agent_id} 已离场。原因：{reason}"
                    
                    for target_id in all_agent_ids:
                        if target_id != self.agent_id:
                            # 检查对方是否在线（可选，但通常给在线的人发记忆更合理）
                            await controller.run_agent_method(
                                target_id,
                                "state",
                                "add_long_term_memory",
                                broadcast_msg
                            )
                    logger.info(f"【{self.agent_id}】下线消息已广播给所有智能体")
                except Exception as broadcast_err:
                    logger.warning(f"【{self.agent_id}】下线消息广播失败: {broadcast_err}")
                
                return True

            return False

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】分析生存状态时出错: {e}")
            return False

    async def _adjust_long_task(self, current_tick: int) -> None:
        """
        根据短期和长期记忆，判断当前LongTask是否需要调整
        """
        try:
            # 获取state组件
            state_component = self._component.agent.get_component("state")
            state_plugin = state_component.get_plugin()

            # 读取当前LongTask
            long_task_str = await state_plugin.get_long_task()

            # 如果任务刚被清空（已完成），则不进行调整
            if not long_task_str:
                return

            logger.info(f"【{self.agent_id}】【{current_tick}】开始判断LongTask是否需要调整: {long_task_str[:50]}...")

            # 获取所有短期记忆和长期记忆
            short_memories = await state_plugin.get_short_term_memory()
            long_memories = await state_plugin.get_long_term_memory()

            short_context = "\n".join([f"- {mem}" for mem in short_memories]) if short_memories else "（暂无）"
            long_context = "\n".join([f"- {mem['content']}" for mem in long_memories]) if long_memories else "（暂无）"

            # 构建判断和调整的prompt
            prompt = f"""你是一个智能体的战略规划助手。请根据以下记忆，判断当前长期任务(LongTask)是否需要根据现状进行调整。

当前长期任务：
{long_task_str}

近期短期记忆：
{short_context}

历史长期记忆：
{long_context}

当前回合数：{current_tick}

要求：
1. 评估当前任务是否仍然符合现状。如果环境发生重大变化、目标已偏离或出现了更紧迫的替代方案，请建议调整。
2. 如果不需要调整，请只返回"无需调整"。
3. 如果需要调整，请返回调整后的新任务内容。新的任务应清晰、具体且具备阶段性目标。
4. 只返回结论（"无需调整"或新任务全文），不要包含任何前缀、解释或多余的文字。

请判断并给出结果："""

            # 调用大模型
            if not self.model:
                logger.error(f"【{self.agent_id}】【{current_tick}】模型未初始化，无法进行LongTask调整判断")
                return

            result = await self.model.chat(prompt)
            result = result.strip()

            if "无需调整" in result and len(result) < 10:
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask现状良好，无需调整")
            else:
                logger.info(f"【{self.agent_id}】【{current_tick}】检测到任务需要调整。")
                logger.info(f"原任务：{long_task_str}")
                logger.info(f"新任务：{result}")
                
                # 直接更新状态
                await state_plugin.set_long_task(result)
                # 记录一条调整记忆
                await state_plugin.add_long_term_memory(f"【任务调整】因环境变化，将长期任务调整为：{result}")
                logger.info(f"【{self.agent_id}】【{current_tick}】LongTask 已成功调整并记录")

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】调整LongTask时出错: {e}")
