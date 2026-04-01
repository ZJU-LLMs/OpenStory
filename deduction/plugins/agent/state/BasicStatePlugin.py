from typing import Callable, Dict, Any, Optional
from agentkernel_distributed.toolkit.logger import get_logger
from agentkernel_distributed.mas.agent.base.plugin_base import StatePlugin
from agentkernel_distributed.types.schemas.action import ActionResult

logger = get_logger(__name__)

class BasicStatePlugin(StatePlugin):
    """
    Agent state plugin.
    """

    def __init__(self, adapter: Callable, state_data: Optional[Dict[str, Any]] = None, agent_id: str = "Unknown") -> None:
        super().__init__()
        self.adapter = adapter
        # 如果 state_data 是字符串（配置键），则初始化为空字典
        if isinstance(state_data, str):
            self.state_data = {}
        else:
            self.state_data = state_data or {}
        self.agent_id = agent_id
        self.current_tick = self.state_data.get('current_tick', 0)
        self.state_data['current_tick'] = self.current_tick
        # 初始化 LongTask 字段
        if 'long_task' not in self.state_data:
            self.state_data['long_task'] = None
        # 初始化短期记忆字典（按tick存储）
        if 'short_term_memory' not in self.state_data:
            self.state_data['short_term_memory'] = {}
        # 兼容旧格式：如果是列表，转换为字典
        elif isinstance(self.state_data['short_term_memory'], list):
            old_list = self.state_data['short_term_memory']
            self.state_data['short_term_memory'] = {i: mem for i, mem in enumerate(old_list)}
        # 初始化长期记忆列表
        if 'long_term_memory' not in self.state_data:
            self.state_data['long_term_memory'] = []
        # 初始化对话历史字典（按tick存储）
        if 'dialogues' not in self.state_data:
            self.state_data['dialogues'] = {}
        # 初始化活跃状态（默认为True）
        if 'is_active' not in self.state_data:
            self.state_data['is_active'] = True
        # 记录不活跃的具体原因
        if 'inactive_reason' not in self.state_data:
            self.state_data['inactive_reason'] = ""
        # 初始化每日时辰计划（按天存储）
        if 'hourly_plans' not in self.state_data:
            self.state_data['hourly_plans'] = {}
        # 兼容旧格式：如果是列表，转换为第一天的计划
        elif isinstance(self.state_data['hourly_plans'], list):
            old_list = self.state_data['hourly_plans']
            self.state_data['hourly_plans'] = {1: old_list}

    async def init(self) -> None:
        """初始化StatePlugin，从component获取agent_id"""
        if hasattr(self, '_component') and self._component and hasattr(self._component, 'agent'):
            self.agent_id = self._component.agent.agent_id
            logger.info(f"【{self.agent_id}】StatePlugin初始化完成")

    async def execute(self, current_tick: int) -> None:
        self.current_tick = current_tick
        self.state_data['current_tick'] = current_tick

    async def get_state(self, key: str = None, default: Any = None) -> Dict[str, Any]:
        """
        获取状态数据

        Args:
            key: 状态键，如果为 None 则返回所有状态
            default: 默认值

        Returns:
            状态数据
        """
        if key is None:
            return self.state_data
        return self.state_data.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        """
        设置单个状态值

        Args:
            key: 状态键
            value: 状态值
        """
        self.state_data[key] = value
        logger.debug(f"【{self.agent_id}】【{self.current_tick}】状态已更新: {key} = {value}")

    async def set_state_batch(self, state: Dict[str, Any]) -> None:
        """
        批量设置状态

        Args:
            state: 状态字典
        """
        self.state_data.update(state)
        logger.debug(f"【{self.agent_id}】【{self.current_tick}】批量更新状态: {list(state.keys())}")

    async def set_long_task(self, long_task_str: str) -> None:
        """
        设置 LongTask 字段

        Args:
            long_task_str: LongTask 的字符串表示
        """
        await self.set_state('long_task', long_task_str)
        logger.info(f"【{self.agent_id}】【{self.current_tick}】LongTask 已设置: {long_task_str}")

    async def get_long_task(self) -> Optional[str]:
        """
        获取 LongTask 字段

        Returns:
            LongTask 的字符串表示，如果不存在则返回 None
        """
        return await self.get_state('long_task')

    async def set_hourly_plans(self, hourly_plans: list) -> None:
        """
        设置12个时辰的计划，按天存储

        Args:
            hourly_plans: 12个时辰的计划列表，格式为 List[List[Any]]
        """
        day = (self.current_tick // 12) + 1
        
        if 'hourly_plans' not in self.state_data or not isinstance(self.state_data['hourly_plans'], dict):
            self.state_data['hourly_plans'] = {}
            
        self.state_data['hourly_plans'][day] = hourly_plans
        logger.info(f"【{self.agent_id}】【{self.current_tick}】第 {day} 天的12个时辰计划已设置，共 {len(hourly_plans)} 个时辰")

    async def get_hourly_plans(self, day: int = None) -> Optional[Any]:
        """
        获取12个时辰的计划

        Args:
            day: 获取第几天的计划，如果为 None 则返回所有天的计划字典

        Returns:
            12个时辰的计划列表或字典，如果不存在则返回 None
        """
        all_plans = await self.get_state('hourly_plans')
        if day is None:
            return all_plans
        if isinstance(all_plans, dict):
            return all_plans.get(day)
        return None

    async def add_short_term_memory(self, memory: str, tick: int = None) -> None:
        """
        添加一条短期记忆，如果该tick已有记忆则覆盖

        Args:
            memory: 记忆内容
            tick: 回合数，如果为None则使用当前tick
        """
        # 忽略对Unknown人的记忆操作
        if self.agent_id == "Unknown":
            logger.debug(f"【Unknown】忽略短期记忆操作")
            return

        if tick is None:
            tick = self.current_tick

        # 短期记忆按tick存储，方便覆盖
        if 'short_term_memory' not in self.state_data:
            self.state_data['short_term_memory'] = {}

        # 如果该tick已有记忆，记录覆盖日志
        if tick in self.state_data['short_term_memory']:
            old_memory = self.state_data['short_term_memory'][tick]
            logger.info(f"【{self.agent_id}】【{tick}】覆盖短期记忆: {old_memory[:30]}... -> {memory[:30]}...")
        else:
            logger.info(f"【{self.agent_id}】【{tick}】添加短期记忆: {memory}")

        self.state_data['short_term_memory'][tick] = memory

    async def get_short_term_memory(self) -> list:
        """
        获取所有短期记忆，按tick排序返回

        Returns:
            短期记忆列表，每个元素为 {'tick': int, 'content': str}
        """
        memories_dict = self.state_data.get('short_term_memory', {})
        if isinstance(memories_dict, list):
            # 兼容旧格式（列表），转换回对象列表
            return [{'tick': i, 'content': mem} for i, mem in enumerate(memories_dict)]

        # 按tick排序返回记忆对象列表
        sorted_ticks = sorted(memories_dict.keys())
        return [{'tick': tick, 'content': memories_dict[tick]} for tick in sorted_ticks]

    async def clear_short_term_memory(self) -> None:
        """
        清空所有短期记忆
        """
        self.state_data['short_term_memory'] = {}
        logger.info(f"【{self.agent_id}】【{self.current_tick}】短期记忆已清空")

    async def add_long_term_memory(self, memory: str) -> None:
        """
        添加一条长期记忆

        Args:
            memory: 记忆内容
        """
        # 忽略对Unknown人的记忆操作
        if self.agent_id == "Unknown":
            logger.debug(f"【Unknown】忽略长期记忆操作")
            return

        if 'long_term_memory' not in self.state_data:
            self.state_data['long_term_memory'] = []

        self.state_data['long_term_memory'].append({
            'tick': self.current_tick,
            'content': memory
        })
        logger.info(f"【{self.agent_id}】【{self.current_tick}】添加长期记忆: {memory[:50]}...")

    async def get_long_term_memory(self) -> list:
        """
        获取所有长期记忆

        Returns:
            长期记忆列表
        """
        return self.state_data.get('long_term_memory', [])

    async def add_dialogue(self, tick: int, history: list) -> None:
        """
        添加对话历史

        Args:
            tick: 回合数
            history: 对话历史列表
        """
        if self.agent_id == "Unknown":
            return

        if 'dialogues' not in self.state_data:
            self.state_data['dialogues'] = {}
        
        self.state_data['dialogues'][tick] = history
        logger.info(f"【{self.agent_id}】【{tick}】保存对话历史，共 {len(history)} 条记录")

    async def get_dialogues(self) -> dict:
        """
        获取所有对话历史

        Returns:
            对话历史字典 {tick: history}
        """
        return self.state_data.get('dialogues', {})

    async def set_active_status(self, is_active: bool, reason: str = "") -> None:
        """
        设置智能体的活跃状态

        Args:
            is_active: 是否活跃
            reason: 原因描述
        """
        self.state_data['is_active'] = is_active
        if reason:
            self.state_data['inactive_reason'] = reason
        logger.warning(f"【{self.agent_id}】状态变更：is_active={is_active}, 原因：{reason}")

    async def is_active(self) -> bool:
        """
        判断智能体是否活跃

        Returns:
            bool: 是否活跃
        """
        return self.state_data.get('is_active', True)

    async def get_inactive_reason(self) -> str:
        """
        获取不活跃的原因

        Returns:
            str: 原因描述
        """
        return self.state_data.get('inactive_reason', "")
