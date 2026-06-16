import os
from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from .matcher import analyze_resume
from .rag_engine import ask_rag

# 1. 终极状态机数据结构定义
class AgentState(TypedDict):
    input_text: str      # 前端用户当前输入的文本
    resume_text: str     # 前端实时解析出来的 PDF 简历纯文本
    intent: str          # 大模型路由器分析出的当前意图
    reply: str           # 最终准备输出给前端渲染的 Markdown 文本
    history: List[Dict]  # 新增：多轮对话历史记忆，结构如 [{"role": "user", "content": "..."}, ...]

# 2. 定义 Agent 动作工具 (Tool Calling)
@tool
def send_interview_email(candidate_name: str, interview_time: str) -> str:
    """
    当用户明确要求给候选人发送面试邀约邮件、通知候选人、或者安排面试时间时，调用此工具。
    参数：
    - candidate_name: 候选人的姓名
    - interview_time: 具体的面试安排时间（例如：明天下午两点、下周二上午10点）
    """
    return f"🚀 **[系统动作]** 已成功对接内网企业邮件网关。已向候选人【{candidate_name}】系统邮箱发送了正式面试邀约，时间定为：{interview_time}。系统已同步更新 HR 日程表。"

# 3. AI-Native 中央意图解析节点（感知多轮历史，根治追问跑偏）
def parse_intent(state: AgentState):
    text = state.get("input_text", "")
    history = state.get("history", [])
    
    # 初始化一个确定性最高（温度为0）的轻量大模型做分类
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        temperature=0.0
    )
    
    system_prompt = """你是一个企业智能 HR 系统的中央意图路由器。
你的核心任务是根据【当前用户的输入】以及提供的【历史对话上下文】，将用户的真实意图精确分类到以下三个通道之一。

你必须且只能输出以下三个单词之一，绝对不能带任何标点符号、解释或多余字符：
- action_tool : 当用户想要执行具体的行政、通知、发信动作时（如：发邮件、发送面试邀约、通知候选人、安排面试、录用等）。
- resume      : 当用户想要评估简历、对比JD、筛选候选人，或者【顺着上文追问/补充关于候选人的能力、技术栈、假设性提问、评分变化】时。
- rag         : 当用户询问公司的通用规章制度、考勤、报销、请假、福利、企业文化等静态文档内容时。

⚠️ 核心上下文推断准则：
如果用户当前的输入非常简短，且包含技术名词（如 React, Vue, Python, 前端），或者包含假设句式（如“那如果他...”、“要是他会...呢”），请务必结合历史对话。如果上文正在聊简历匹配和评估，这属于 resume 通道。

示例：
历史：[用户: 帮我评估张三的简历, 助手: 匹配度为65分...] -> 当前用户: "那如果他自学过半年的 React 呢？" -> 输出：resume
历史：[] -> 当前用户: "北京出差报销标准是什么？" -> 输出：rag
历史：[用户: 评估完李四了] -> 当前用户: "帮他发个明天的面试邀约吧" -> 输出：action_tool
"""

    # 格式化历史记忆，喂给大模型路由器
    formatted_history = ""
    if history:
        formatted_history = "【历史对话上下文】:\n"
        for msg in history[-6:]: # 取最近3轮对话（1轮=1个user+1个assistant），防止 token 爆炸
            role = "用户" if msg.get("role") == "user" else "助手"
            formatted_history += f"{role}: {msg.get('content')}\n"
            
    user_content = f"{formatted_history}\n【当前用户输入】: '{text}'\n\n请输出分类结果："

    try:
        response = llm.invoke([
            ("system", system_prompt),
            ("user", user_content)
        ])
        intent_result = response.content.strip().lower()
        
        if "action_tool" in intent_result:
            return {"intent": "action_tool"}
        elif "resume" in intent_result:
            return {"intent": "resume"}
        elif "rag" in intent_result:
            return {"intent": "rag"}
            
    except Exception as e:
        print(f"[LLM Router Warning] 接口调用异常: {e}，启动硬编码关键词防御机制。")
        
    # 【高可用降级防御】若 API 超时，自动降级到高级关键词粗暴拦截
    text_lower = text.lower()
    if any(x in text_lower for x in ["邮件", "发件", "邀约", "通知", "发通知", "录用", "安排"]):
        return {"intent": "action_tool"}
    elif any(x in text_lower for x in ["简历", "匹配", "评估", "jd", "react", "前端", "开发", "技术", "能力", "学过", "自学", "如果他"]):
        return {"intent": "resume"}
    return {"intent": "rag"}

# 4. 企业级 RAG 知识问答业务节点
def handle_rag(state: AgentState):
    question = state["input_text"]
    real_answer = ask_rag(question)
    return {"reply": real_answer}

# 5. 全栈动态简历评估节点
def handle_resume(state: AgentState):
    resume_content = state.get("resume_text", "").strip()
    
    # 健壮性防错：如果前端没有成功上传/提取到文本，及时中断并提醒
    if not resume_content:
        return {"reply": "⚠️ **系统提示**：检测到您尚未在左侧面板上传任何候选人简历（PDF格式）。为了进行精准评估，请先在左侧上传文件后再试。"}
        
    # 如果用户当前是在追问（如“如果他学过 React”），为了把信息带给 matcher，我们需要合并上下文
    user_msg = state["input_text"]
    history = state.get("history", [])
    
    # 调用底层的 JSON 强制匹配引擎
    result = analyze_resume(
        resume_text=f"{resume_content}\n[附加补充/多轮追问上下文]: {user_msg}", 
        jd_text=user_msg if "希望你" in user_msg or "职位" in user_msg else "请参考左侧粘贴的JD进行连续对比评估"
    )
    
    pros_list = result.get('pros', [])
    cons_list = result.get('cons', [])
    
    pros_markdown = "\n".join([f"{i+1}️⃣ {item}" for i, item in enumerate(pros_list)]) if pros_list else "暂无明显核心优势"
    cons_markdown = "\n".join([f"{i+1}️⃣ {item}" for i, item in enumerate(cons_list)]) if cons_list else "暂无明显潜在短板"
    
    formatted_reply = f"""
### 📊 候选人综合评估报告

* **实时综合匹配度评分**：  
  # 🎯 **{result.get('score', 0)} 分**
  
---

### 🌟 核心优势 (Pros)
{pros_markdown}

### ⚠️ 潜在短板 (Cons)
{cons_markdown}
"""
    return {"reply": formatted_reply}

# 6. Tool Calling（行政动作调度）节点
def handle_action_tool(state: AgentState):
    user_msg = state["input_text"]
    
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE")
    )
    
    # 动态将发邮件的工具绑定给大模型
    llm_with_tools = llm.bind_tools([send_interview_email])
    ai_msg = llm_with_tools.invoke(f"用户当前说的话：'{user_msg}'。请判断是否需要发送邮件，若需要，请提取姓名和时间。")
    
    if ai_msg.tool_calls:
        tool_call = ai_msg.tool_calls[0]
        args = tool_call["args"]
        # 通过 invoke 触发工具执行
        tool_output = send_interview_email.invoke(args)
        return {"reply": tool_output}
    else:
        return {"reply": "🤖 已经捕获到您的操作意图，但未能从您的话语中分析出明确的【候选人姓名】或【面试时间】。请更清晰地对我说，例如：'帮我给张伟发送明天下午两点的面试邀约'。"}

# 7. 动态路由条件连线逻辑
def router(state: AgentState):
    if state["intent"] == "action_tool":
        return "tool_node"
    elif state["intent"] == "resume":
        return "resume_node"
    return "rag_node"

# 8. 图状态机体系组装与编译
workflow = StateGraph(AgentState)

# 注册节点
workflow.add_node("intent_node", parse_intent)
workflow.add_node("rag_node", handle_rag)
workflow.add_node("resume_node", handle_resume)
workflow.add_node("tool_node", handle_action_tool)

# 设置默认入口
workflow.set_entry_point("intent_node")

# 绑定动态路由边
workflow.add_conditional_edges(
    "intent_node", 
    router,
    {
        "tool_node": "tool_node",
        "resume_node": "resume_node",
        "rag_node": "rag_node"
    }
)

# 终点闭环
workflow.add_edge("rag_node", END)
workflow.add_edge("resume_node", END)
workflow.add_edge("tool_node", END)

# 💡 终极进化：引入云端与本地通用的 MemorySaver 开启跨多轮对话状态持久化
agent_app = workflow.compile(checkpointer=MemorySaver())