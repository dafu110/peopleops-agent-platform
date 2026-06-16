import streamlit as st
import time
from core.workflow import agent_app
from pypdf import PdfReader

# 1. 页面基本配置
st.set_page_config(page_title="AI Personnel Manager", layout="wide")
st.title("💼 AI-Native 智能人事大管家")

# 初始化用于缓存侧边栏 PDF 简历纯文本的全局状态
if "extracted_resume_text" not in st.session_state:
    st.session_state["extracted_resume_text"] = ""

# --- 2. 📂 侧边栏输入面板配置 ---
with st.sidebar:
    st.header("📂 招聘输入面板")
    uploaded_resume = st.file_uploader("第一步：上传候选人简历 (PDF)", type=["pdf"])
    
    # 💡 全栈动态流：只要检测到文件上传，立刻实时解析 PDF 文本
    if uploaded_resume is not None:
        try:
            # 增加一个局部小加载圈，防止大文件卡顿影响用户体验
            with st.spinner("正在实时提取 PDF 简历文本..."):
                reader = PdfReader(uploaded_resume)
                text_content = ""
                for page in reader.pages:
                    text_content += page.extract_text() + "\n"
                
                # 将解析出的纯文本存入页面级缓存
                st.session_state["extracted_resume_text"] = text_content
                st.success("✅ 简历文本动态解析成功！")
        except Exception as e:
            st.error(f"❌ 简历解析失败: {str(e)}")
    else:
        # 用户清空或撤销上传的文件时，清空缓存
        st.session_state["extracted_resume_text"] = ""

    # JD 输入框
    jd_input = st.text_area(
        "第二步：输入岗位职业描述 (JD)", 
        height=300, 
        placeholder="请在此粘贴 Boss直聘 等平台的职位描述内容..."
    )

# --- 3. 💬 主对话区历史记录渲染 ---
if "messages" not in st.session_state:
    # 引导语清晰指明三大企业级 Agent 能力，方便面试现场直接展示
    st.session_state.messages = [{
        "role": "assistant", 
        "content": "您好！我是您的智能 HRBP 助手。我已经完成了全新升级，现在支持：\n1. 🏢 **企业规章制度查阅**（自动附带官方 PDF 页码引用与溯源）\n2. 📊 **全栈动态简历评估**（直接解析左侧上传的 PDF 进行严格的 JSON 结构化打分）\n3. 🧠 **上下文感知多轮追问**（大模型动态意图分发，记得上文，根治追问跑偏）\n4. 🚀 **行政动作工具调用**（语义触发 Tool Calling，如模拟自动发送面试邀约邮件）"
    }]

# 渲染历史对话
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 4. 🧠 用户交互与 LangGraph 记忆闭环 ---
if user_input := st.chat_input("请输入您的问题..."):
    # 1. 实时渲染用户输入
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
        
    # 2. 准备渲染助手的流式输出
    with st.chat_message("assistant"):
        # 建立一个 Streamlit 动态空容器，用来承接平滑的打字机滚动效果
        response_placeholder = st.empty()
        
        try:
            # 💡 关键点 1：配置跨多轮对话的 thread_id，激活后端的 MemorySaver 持久化机制
            config = {"configurable": {"thread_id": "hr_session_001"}}
            
            # 业务分流逻辑（如果是首轮评估简历，则将左侧的 JD 内容作为主输入送给 matcher 比对）
            current_jd = jd_input.strip()
            if any(x in user_input for x in ["简历", "匹配", "评估", "JD"]) and current_jd:
                final_input_text = current_jd
            else:
                final_input_text = user_input

            # 💡 关键点 2：将前端历史消息数组 st.session_state.messages 完整打包作为 "history" 参数送给后端
            inputs = {
                "input_text": final_input_text, 
                "resume_text": st.session_state["extracted_resume_text"],
                "intent": "", 
                "reply": "",
                "history": st.session_state.messages  # 完美闭环：赋予后端中央路由器历史感知能力
            }
            
            # 3. 触发有历史记忆、有工具调度能力的 LangGraph 状态机
            output = agent_app.invoke(inputs, config)
            full_response = output.get("reply", "抱歉，系统未能成功生成有效回复。")
            
            # 💡 关键点 3：商业级 AI 产品的流式（Streaming）打字机 UX 渲染
            displayed_text = ""
            # 将后端吐出的完整 Markdown 拆成单字符流进行平滑滚动输出
            for chunk in full_response:
                displayed_text += chunk
                response_placeholder.markdown(displayed_text + "▌") # 带有炫酷的打字光标效果
                time.sleep(0.003)  # 毫秒级微调速度，极其丝滑
                
            # 最终渲染去光标的干净 Markdown
            response_placeholder.markdown(full_response)
            
            # 4. 将助手的回答记录进全局历史消息中
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            
        except Exception as e:
            st.error(f"❌ 运行发生错误: {str(e)}")