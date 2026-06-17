import time
from uuid import uuid4

import streamlit as st

from core.audit import write_audit_event
from core.config import get_settings
from core.database import init_db, list_interview_actions
from core.pdf_utils import extract_pdf_text
from core.security import stable_hash, verify_password
from core.workflow import agent_app


settings = get_settings()
init_db()
st.set_page_config(page_title=settings.app_name, page_icon="💼", layout="wide")
st.title(f"💼 {settings.app_name}")


@st.cache_data(show_spinner=False)
def cached_extract_pdf_text(file_bytes: bytes) -> str:
    return extract_pdf_text(file_bytes)


def init_state() -> None:
    st.session_state.setdefault("extracted_resume_text", "")
    st.session_state.setdefault("thread_id", f"peopleops_session_{uuid4().hex[:8]}")
    st.session_state.setdefault("authenticated", not bool(settings.access_password))
    st.session_state.setdefault(
        "messages",
        [
            {
                "role": "assistant",
                "content": (
                    "您好，我是 PeopleOps Agent。您可以上传候选人简历并粘贴 JD 做匹配评估，"
                    "也可以询问员工手册、考勤、报销、福利等制度问题。"
                ),
            }
        ],
    )


def render_stream(text: str) -> None:
    placeholder = st.empty()
    displayed = ""
    for chunk in text:
        displayed += chunk
        placeholder.markdown(displayed + "▌")
        time.sleep(0.002)
    placeholder.markdown(text)


def require_access() -> None:
    if st.session_state.get("authenticated"):
        return

    st.info("请输入访问口令以进入 PeopleOps Agent Platform。")
    password = st.text_input("访问口令", type="password")
    if st.button("进入", type="primary"):
        if verify_password(password, settings.access_password):
            st.session_state["authenticated"] = True
            write_audit_event("auth.login_success", {"session_id": st.session_state["thread_id"]})
            st.rerun()
        write_audit_event("auth.login_failed", {"session_id": st.session_state["thread_id"]})
        st.error("访问口令不正确。")
    st.stop()


init_state()
require_access()

with st.sidebar:
    st.header("工作台")
    st.caption(f"会话：{st.session_state['thread_id']}")
    st.caption(f"工具模式：{settings.tool_execution_mode}")
    st.caption(f"向量库：{settings.chroma_persist_dir.name}")
    st.caption(f"审计日志：{settings.audit_log_path.name}")

    uploaded_resume = st.file_uploader("上传候选人简历（PDF）", type=["pdf"])

    if uploaded_resume is not None:
        try:
            with st.spinner("正在提取简历文本..."):
                text_content = cached_extract_pdf_text(uploaded_resume.getvalue())
            st.session_state["extracted_resume_text"] = text_content
            if text_content:
                write_audit_event(
                    "resume.uploaded",
                    {
                        "session_id": st.session_state["thread_id"],
                        "filename": uploaded_resume.name,
                        "content_hash": stable_hash(text_content),
                        "char_count": len(text_content),
                    },
                )
                st.success("简历文本提取成功")
            else:
                st.warning("PDF 未提取到可用文本，可能是扫描件或图片型简历。")
        except Exception as exc:
            st.session_state["extracted_resume_text"] = ""
            write_audit_event(
                "resume.upload_failed",
                {"session_id": st.session_state["thread_id"], "error": str(exc)},
            )
            st.error(f"简历解析失败：{exc}")
    else:
        st.session_state["extracted_resume_text"] = ""

    jd_input = st.text_area(
        "岗位描述（JD）",
        height=260,
        placeholder="粘贴岗位职责、任职要求、技术栈、年限要求等信息...",
    )

    st.divider()
    st.subheader("运行检查")
    st.caption(f"知识库：{settings.policy_pdf_path.name}")
    if not settings.policy_pdf_path.exists():
        st.warning("未找到企业知识库 PDF，请检查 HR_POLICY_PDF 配置。")
    if not settings.has_llm_config:
        st.warning("未配置 OPENAI_API_KEY 或 OPENAI_API_BASE，系统将只能使用部分降级能力。")
    if settings.access_password:
        st.success("访问控制已开启")
    else:
        st.warning("访问控制未开启，可配置 ACCESS_PASSWORD。")

    st.divider()
    st.subheader("最近工具动作")
    for action in list_interview_actions(limit=5):
        st.caption(
            f"#{action['id']} {action['status']} | {action['candidate_name']} | {action['interview_time']}"
        )


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


if user_input := st.chat_input("请输入 HR 问题、制度问题或候选人评估需求..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    write_audit_event(
        "chat.user_message",
        {"session_id": st.session_state["thread_id"], "input_text": user_input},
    )
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            inputs = {
                "input_text": user_input,
                "resume_text": st.session_state["extracted_resume_text"],
                "jd_text": jd_input.strip(),
                "intent": "",
                "reply": "",
                "history": st.session_state.messages,
            }
            config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
            output = agent_app.invoke(inputs, config)
            full_response = output.get("reply") or "抱歉，系统未能生成有效回复。"
            render_stream(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            write_audit_event(
                "chat.assistant_message",
                {
                    "session_id": st.session_state["thread_id"],
                    "intent": output.get("intent", ""),
                    "reply_preview": full_response[:500],
                },
            )
        except Exception as exc:
            write_audit_event(
                "chat.error",
                {"session_id": st.session_state["thread_id"], "error": str(exc)},
            )
            st.error(f"运行发生错误：{exc}")
