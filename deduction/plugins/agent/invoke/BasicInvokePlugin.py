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
        logger.info(f"【{self.agent_id}】【N/A】BasicInvokePlugin 初始化完成")

    async def execute(self, current_tick: int) -> None:
        """
        Execute the Invoke Plugin at every system tick.

        Args:
            current_tick (int): The system current tick.
        """
        try:
            # 获取相关组件
            state_component = self._component.agent.get_component("state")
            profile_component = self._component.agent.get_component("profile")

            state_plugin = state_component.get_plugin()
            profile_plugin = profile_component.get_plugin()

            # 检查是否活跃
            if not await state_plugin.is_active():
                # logger.debug(f"【{self.agent_id}】【{current_tick}】智能体已下线，跳过执行")
                return

            # 获取当前天的计划 (每12个tick为一天)
            current_day = (current_tick // 12) + 1
            hourly_plans = await state_plugin.get_hourly_plans(day=current_day)

            # 计算当前时辰 (0-12)
            current_hour = current_tick % 12

            # 找到当前时辰的计划
            current_plan = None
            if hourly_plans:
                for plan in hourly_plans:
                    # plan格式: [action, time, target, location, importance]
                    if len(plan) >= 5 and plan[1] == current_hour:
                        current_plan = plan
                        break
            else:
                logger.debug(f"【{self.agent_id}】【{current_tick}】没有第 {current_day} 天的时辰计划")

            # 检查是否有用户设定的最高优先级计划
            user_plan_key = f"user_plan:{self.agent_id}"
            user_plan_data_str = await self.redis.get(user_plan_key)
            if user_plan_data_str:
                try:
                    import json
                    if isinstance(user_plan_data_str, str):
                        user_plan_data = json.loads(user_plan_data_str)
                    else:
                        user_plan_data = user_plan_data_str
                    
                    # 检查是否是针对当前tick的计划
                    if user_plan_data.get('tick') == current_tick:
                        logger.info(f"【{self.agent_id}】【{current_tick}】检测到用户设定的最高优先级计划！")
                        current_plan = [
                            user_plan_data.get('action', '执行用户计划'),
                            current_hour,
                            user_plan_data.get('target', '无'),
                            user_plan_data.get('location', ''),
                            999  # 最高优先级
                        ]
                        # 执行后删除该计划，避免重复
                        await self.redis.delete(user_plan_key)
                except Exception as e:
                    logger.warning(f"【{self.agent_id}】【{current_tick}】解析用户计划失败: {e}")

            if not current_plan:
                logger.debug(f"【{self.agent_id}】【{current_tick}】当前时辰 {current_hour} 没有对应的计划")
                await state_plugin.set_state('current_plan', None)
                await state_plugin.set_state('occupied_by', None)
                await state_plugin.set_state('current_action', None)
                
                # 记录“休息”状态的短期记忆，防止 Tick 缺失
                idle_desc = f"{self.agent_id} 此时没有具体的计划，正在稍作休息。"
                await state_plugin.add_short_term_memory(idle_desc, tick=current_tick)
                return

            # 将当前计划存储到 state 中，供前端展示
            await state_plugin.set_state('current_plan', current_plan)

            # 解析计划
            action = current_plan[0]
            time = current_plan[1]
            target = current_plan[2]
            location = current_plan[3]
            importance = current_plan[4]

            # 如果重要性低于7，等待5秒让高优先级任务先执行
            if importance < 7:
                import asyncio
                await asyncio.sleep(5)
                logger.debug(f"【{self.agent_id}】【{current_tick}】低优先级任务等待5秒后执行")

            # 检查自己是否被占用
            occupation_info = await self._get_occupation(current_tick, self.agent_id)
            if occupation_info:
                occupier = occupation_info.get("occupier")
                occupier_importance = occupation_info.get("importance", 0)
                
                # 如果被别人占用且对方优先级更高
                if occupier != self.agent_id and occupier_importance > importance:
                    logger.info(f"【{self.agent_id}】【{current_tick}】被更高优先级的人 {occupier} 占用，跳过执行原计划")
                    # 在状态中记录被谁占用以及对方的动作
                    await state_plugin.set_state('occupied_by', occupation_info)
                    
                    # 记录被占用的描述
                    occupier_name = occupier.split('.')[-1] # 简单提取名字
                    occupier_action = occupation_info.get("action", "某项事务")
                    busy_desc = f"正在协助 {occupier_name} 处理 {occupier_action}。"
                    
                    # 先在自己这边添加短期记忆，确保 Tick 不缺失
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    # 同时设置 current_action 为占用者的动作，确保前端显示“当前行动”
                    await state_plugin.set_state('current_action', busy_desc)
                    return
            
            # 如果没被别人占用，清除占用信息
            await state_plugin.set_state('occupied_by', None)

            # 占用自己（如果已被他人抢先占用则放弃）
            if not await self._occupy(current_tick, importance, action, location):
                # 重新读取占用信息，走被占用的处理分支
                occupation_info = await self._get_occupation(current_tick, self.agent_id)
                if occupation_info:
                    occupier_name = occupation_info.get("occupier", "").split('.')[-1]
                    occupier_action = occupation_info.get("action", "某项事务")
                    busy_desc = f"正在协助 {occupier_name} 处理 {occupier_action}。"
                    await state_plugin.set_state('occupied_by', occupation_info)
                    await state_plugin.add_short_term_memory(busy_desc, tick=current_tick)
                    await state_plugin.set_state('current_action', busy_desc)
                return

            logger.info(f"【{self.agent_id}】【{current_tick}】执行时辰 {time} 的计划: {action}")

            # 获取自己的profile
            self_profile = profile_plugin.get_agent_profile()

            # 获取target的profile（如果target存在）
            target_profile = None
            plan_note = None  # 计划注释
            target_participated = False  # 记录目标是否参与了互动
            if target and target != "无" and target != "自己":
                target_profile = await profile_plugin.get_agent_profile_by_id(target)
                if not target_profile:
                    logger.warning(f"【{self.agent_id}】【{current_tick}】无法获取目标 {target} 的档案")
                else:
                    # 尝试占用目标
                    if not await self._try_occupy_target(current_tick, target, importance, action):
                        plan_note = f"注意：{target}正被其他人占用，无法配合"
                        logger.info(f"【{self.agent_id}】【{current_tick}】{plan_note}")
                        # 记录到状态中，供前端展示
                        await state_plugin.set_state('current_plan_note', plan_note)
                    else:
                        target_participated = True  # 占用成功，目标参与了互动
                        await state_plugin.set_state('current_plan_note', None)
            else:
                await state_plugin.set_state('current_plan_note', None)

            # 生成执行描述（只在重要性≥7时使用LLM生成详细描述）
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
                    # 保存对话历史
                    if dialogue_history:
                        await state_plugin.add_dialogue(current_tick, dialogue_history)
                else:
                    description = description_data
                    dialogue_history = []
            else:
                # 低重要性行动使用简单模板
                self_name = self_profile.get('id', '未知')
                description = f"{self_name}在{location}{action}。"
                dialogue_history = []
                logger.info(f"【{self.agent_id}】【{current_tick}】使用简单模板生成描述（重要性{importance}）")

            # 将描述添加到短期记忆（按tick存储，可覆盖）
            await state_plugin.add_short_term_memory(description, tick=current_tick)
            # 同时将当前正在进行的详细描述存入 state，供前端“当前行动”展示更丰富的内容
            await state_plugin.set_state('current_action', description)
            logger.info(f"【{self.agent_id}】【{current_tick}】已生成并保存执行描述")

            # 如果目标参与了互动，也给目标添加记忆
            if target_participated:
                try:
                    controller = self._component.agent.controller
                    # 给参与者设置 occupied_by，确保前端能显示被占用状态
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
                    # 给参与者设置 current_plan（包含位置信息），确保前端能显示正确位置
                    target_plan = [action, time, self.agent_id, location, importance]
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_plan",
                        target_plan
                    )
                    # 给参与者添加记忆
                    await controller.run_agent_method(
                        target,
                        "state",
                        "add_short_term_memory",
                        description,
                        current_tick
                    )
                    # 给参与者也设置当前行动描述，确保前端能看到
                    await controller.run_agent_method(
                        target,
                        "state",
                        "set_state",
                        "current_action",
                        description
                    )
                    # 给参与者也保存对话历史
                    if dialogue_history:
                        await controller.run_agent_method(
                            target,
                            "state",
                            "add_dialogue",
                            current_tick,
                            dialogue_history
                        )
                    logger.info(f"【{self.agent_id}】【{current_tick}】已将执行描述和对话历史添加到参与者 {target} 的状态中")
                except Exception as e:
                    logger.warning(f"【{self.agent_id}】【{current_tick}】无法给参与者 {target} 添加状态: {e}")

        except Exception as e:
            logger.error(f"【{self.agent_id}】【{current_tick}】执行 InvokePlugin 时出错: {e}")

    async def _is_occupied_by_others(self, tick: int, my_importance: int) -> bool:
        """
        检查自己是否被其他更高优先级的人占用

        Args:
            tick: 当前tick
            my_importance: 自己的重要性分数

        Returns:
            bool: 如果被占用返回True，否则返回False
        """
        try:
            key = f"occupation:{tick}:{self.agent_id}"
            occupation_data = await self.redis.get(key)
            if not occupation_data:
                return False

            occupier = occupation_data.get("occupier")
            occupier_importance = occupation_data.get("importance", 0)

            # 如果占用者是自己，不算被占用
            if occupier == self.agent_id:
                return False

            # 如果占用者优先级更高，则被占用
            if occupier_importance > my_importance:
                return True

            return False
        except Exception as e:
            logger.warning(f"【{self.agent_id}】【{tick}】检查占用状态失败: {e}")
            return False

    async def _occupy(self, tick: int, importance: int, action: str, location: str = "") -> bool:
        """
        占用自己（仅当未被他人占用时才写入）

        Returns:
            bool: 成功占用返回True，已被他人占用返回False
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
                # 已被他人占用且对方优先级更高，不覆盖
                if occupier != self.agent_id and occupier_importance > importance:
                    logger.info(f"【{self.agent_id}】【{tick}】自占失败：已被 {occupier}（重要性{occupier_importance}）占用")
                    return False
            await self.redis.set(key, json.dumps({
                "occupier": self.agent_id,
                "importance": importance,
                "action": action,
                "location": location,
            }))
            logger.debug(f"【{self.agent_id}】【{tick}】已占用自己（重要性{importance}，动作：{action}）")
            return True
        except Exception as e:
            logger.warning(f"【{self.agent_id}】【{tick}】占用自己失败: {e}")
            return False

    async def _get_occupation(self, tick: int, target_id: str) -> dict:
        """
        获取目标的占用信息

        Args:
            tick: 当前tick
            target_id: 目标agent_id

        Returns:
            dict: 占用信息，如果未被占用返回None
        """
        try:
            key = f"occupation:{tick}:{target_id}"
            return await self.redis.get(key)
        except Exception as e:
            logger.warning(f"【{self.agent_id}】【{tick}】获取目标 {target_id} 的占用信息失败: {e}")
            return None

    async def _try_occupy_target(self, tick: int, target_id: str, my_importance: int, action: str) -> bool:
        """
        尝试占用目标

        Args:
            tick: 当前tick
            target_id: 目标agent_id
            my_importance: 自己的重要性分数
            action: 自己的动作描述

        Returns:
            bool: 如果成功占用返回True，否则返回False
        """
        try:
            import json
            occupation_info = await self._get_occupation(tick, target_id)

            # 如果目标未被占用，直接占用
            if not occupation_info:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.debug(f"【{self.agent_id}】【{tick}】成功占用目标 {target_id}（重要性{my_importance}，动作：{action}）")
                return True

            # 如果已被占用，检查优先级
            if isinstance(occupation_info, str):
                occupation_info = json.loads(occupation_info)
            occupier = occupation_info.get("occupier")
            occupier_importance = occupation_info.get("importance", 0)

            # 如果占用者是自己，返回成功
            if occupier == self.agent_id:
                return True

            # 如果自己优先级更高，覆盖占用
            if my_importance > occupier_importance:
                key = f"occupation:{tick}:{target_id}"
                await self.redis.set(key, json.dumps({
                    "occupier": self.agent_id,
                    "importance": my_importance,
                    "action": action
                }))
                logger.info(f"【{self.agent_id}】【{tick}】覆盖占用目标 {target_id}（自己{my_importance} > {occupier}{occupier_importance}，动作：{action}）")
                return True

            # 优先级不够，占用失败
            logger.info(f"【{self.agent_id}】【{tick}】无法占用目标 {target_id}（自己{my_importance} <= {occupier}{occupier_importance}）")
            return False

        except Exception as e:
            logger.warning(f"【{self.agent_id}】【{tick}】尝试占用目标 {target_id} 失败: {e}")
            return False

    async def _get_target_importance(self, target_agent_id: str, current_hour: int) -> int:
        """
        获取目标人物在当前时辰的任务重要性分数

        Args:
            target_agent_id: 目标人物ID
            current_hour: 当前时辰 (0-11)

        Returns:
            int: 目标人物的重要性分数，如果无法获取则返回None
        """
        try:
            # 通过controller获取目标agent的state组件
            controller = self._component.agent.controller
            target_hourly_plans = await controller.run_agent_method(
                target_agent_id,
                "state",
                "get_hourly_plans"
            )

            if not target_hourly_plans:
                logger.debug(f"【{self.agent_id}】目标 {target_agent_id} 没有时辰计划")
                return None

            # 找到目标在当前时辰的计划
            for plan in target_hourly_plans:
                # plan格式: [action, time, target, location, importance]
                if len(plan) >= 5 and plan[1] == current_hour:
                    return plan[4]  # 返回重要性分数

            logger.debug(f"【{self.agent_id}】目标 {target_agent_id} 在时辰 {current_hour} 没有计划")
            return None

        except Exception as e:
            logger.warning(f"【{self.agent_id}】获取目标 {target_agent_id} 的重要性分数失败: {e}")
            return None

    async def _get_agent_memory(self, agent_id: str) -> str:
        """获取智能体的短期记忆和长期记忆"""
        try:
            controller = self._component.agent.controller
            short_memory = await controller.run_agent_method(agent_id, "state", "get_short_term_memory")
            long_memory = await controller.run_agent_method(agent_id, "state", "get_long_term_memory")
            
            memory_text = ""
            if long_memory:
                memory_text += "【长期记忆】\n"
                memory_text += "\n".join([f"- {m['content']}" for m in long_memory]) + "\n\n"
            
            if short_memory:
                memory_text += "【近期记忆】\n"
                memory_text += "\n".join([f"- {m}" for m in short_memory[-5:]])  # 最近5条记忆
                
            if not memory_text:
                return "无记忆"
            return memory_text.strip()
        except Exception as e:
            logger.warning(f"获取 {agent_id} 记忆失败: {e}")
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
        模拟智能体对话生成执行描述

        Args:
            agent_id: 智能体ID
            current_tick: 当前回合数
            action: 行动描述
            target: 目标人物
            location: 地点
            importance: 重要性分数
            self_profile: 自己的档案
            target_profile: 目标人物的档案
            plan_note: 计划注释

        Returns:
            Dict[str, Any]: 包含总结 (summary) 和对话历史 (history) 的字典
        """
        default_res = {"summary": f"{self_profile.get('id', '未知')}在{location}{action}。", "history": []}
        if not self.model:
            return default_res

        # 确定参与者
        participants = [agent_id]
        absent_people = []  # 记录因为忙而没来的人

        if target and target not in ["自己", "无", "None", ""]:
            if plan_note:  # 目标正忙，没来
                absent_people.append(target)
            else:
                participants.append(target)

        # 单人行动，使用简单描述
        if len(participants) == 1:
            if absent_people:
                absent_names = ", ".join(absent_people)
                summary = f"{self_profile.get('id', '未知')}在{location}准备{action}，但{absent_names}正忙没来。"
                return {"summary": summary, "history": []}
            else:
                return default_res

        # 多人对话
        try:
            dialogue_history = []
            max_rounds = 10
            current_speaker_idx = 0

            for round_num in range(max_rounds):
                speaker_id = participants[current_speaker_idx]

                # 获取说话者信息
                if speaker_id == agent_id:
                    speaker_profile = self_profile
                else:
                    speaker_profile = target_profile or {}

                speaker_name = speaker_profile.get('id', speaker_id)
                speaker_memory = await self._get_agent_memory(speaker_id)

                # 构建prompt
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

                # 添加其他参与者信息
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

{speaker_name}说："""

                response = await self.model.chat(prompt)
                response = response.strip()

                dialogue_line = f"{speaker_name}：{response}"
                dialogue_history.append(dialogue_line)
                logger.info(f"【{current_tick}】对话第{round_num+1}轮: {dialogue_line}")

                # 检查是否结束
                if "[END]" in response or "END" in response:
                    break

                # 轮换说话者
                current_speaker_idx = (current_speaker_idx + 1) % len(participants)

            # 生成总结
            summary_prompt = f"""以下是{', '.join([p for p in participants])}在{location}的对话：

{chr(10).join(dialogue_history)}

请用一段话（50-100字）总结这次互动，使用第三人称叙述。只返回总结内容，不要其他文字。

【重要】如果对话中发生了以下致命事件，必须在总结中明确写出：
- 死亡事件：必须写出"XX死亡"或"XX被打死/杀死/身亡"，不能含糊其辞
- 重伤事件：必须写出"XX重伤"或"XX奄奄一息"
- 离场事件：必须写出"XX离开"或"XX消失"
这些致命信息是系统判断角色状态的关键，务必清晰明确！"""

            summary = await self.model.chat(summary_prompt)
            summary = summary.strip()
            logger.info(f"【{current_tick}】对话总结: {summary}")
            return {"summary": summary, "history": dialogue_history}

        except Exception as e:
            logger.error(f"【{agent_id}】【{current_tick}】生成对话失败: {e}")
            return default_res

    @property
    def get_last_tick_actions(self) -> List[Dict[str, Any]]:
        """
        返回上一个 tick 的 action 执行记录。

        Returns:
            List[Dict[str, Any]]: 上一个 tick 的 action 执行记录列表。
        """
        pass