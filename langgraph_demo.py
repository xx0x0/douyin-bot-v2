#!/usr/bin/env python3
"""LangGraph 多 agent 协作 demo"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator


class AgentState(TypedDict):
    """共享状态"""
    task: str
    bot_analysis: str
    oa_issues: str
    report: str
    error: str


def analyze_bot(state: AgentState) -> AgentState:
    """Agent 1: 分析 bot.py"""
    print("🤖 Agent 1: 正在分析 douyin-bot...")
    # 这里可以调用 Claude API 或其他工具
    state["bot_analysis"] = "视频下载逻辑正常，建议优化错误处理"
    return state


def check_oa_issues(state: AgentState) -> AgentState:
    """Agent 2: 检查 OA 问题"""
    print("📋 Agent 2: 正在检查 OA 系统...")
    # 这里可以查 TG 消息、读 Google Sheet
    state["oa_issues"] = "发现 3 个未解决问题，2 个已完成"
    return state


def generate_report(state: AgentState) -> AgentState:
    """Agent 3: 生成报告"""
    print("📝 Agent 3: 正在生成周报...")
    state["report"] = f"""
本周工作总结：
1. douyin-bot: {state['bot_analysis']}
2. OA 系统: {state['oa_issues']}
"""
    return state


def should_continue(state: AgentState) -> str:
    """决策函数：是否继续"""
    if state.get("error"):
        return "error"
    return "continue"


# 构建工作流
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("analyze_bot", analyze_bot)
workflow.add_node("check_oa", check_oa_issues)
workflow.add_node("generate_report", generate_report)

# 定义流程
workflow.set_entry_point("analyze_bot")
workflow.add_edge("analyze_bot", "check_oa")
workflow.add_edge("check_oa", "generate_report")
workflow.add_edge("generate_report", END)

# 编译
app = workflow.compile()

if __name__ == "__main__":
    # 执行工作流
    result = app.invoke({
        "task": "生成本周工作总结",
        "bot_analysis": "",
        "oa_issues": "",
        "report": "",
        "error": ""
    })

    print("\n" + "="*50)
    print("✅ 工作流完成")
    print("="*50)
    print(result["report"])
