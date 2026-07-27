"""
GraphCampus 前端可复用组件包

已实现组件：
- interrupt_modal: 中断交互弹窗（确认/编辑/链路预测）
- chat_ui: 对话 UI 组件（消息气泡/输入框/历史记录）
- loading_states: 通用状态组件（空状态/加载态/错误态/骨架屏）
- source_card: 来源引用卡片组件（单卡/列表/内联）
- course_card: 课程概览卡片组件（课程列表/总结卡片）
- error_handler: 统一错误处理组件（ErrorCode→UI映射+兜底交互）

待实现组件：
- graph_viz: 图谱可视化
"""

__all__ = [
    "interrupt_modal",
    "chat_ui",
    "loading_states",
    "source_card",
    "course_card",
    "error_handler",
]
