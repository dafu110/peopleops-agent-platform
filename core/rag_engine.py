import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

# 全局初始化，避免每次提问都重新加载切分文档
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
pdf_path = "data/员工手册测试版.pdf"

if os.path.exists(pdf_path):
    loader = PyPDFLoader(pdf_path)
    # 切小一点，保证精度
    splits = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=40).split_documents(loader.load())
    vectorstore = Chroma.from_documents(documents=splits, embedding=embedding_model)
    global_retriever = vectorstore.as_retriever(search_kwargs={"k": 2})
else:
    global_retriever = None

def ask_rag(question: str) -> str:
    if global_retriever is None or not os.path.exists(pdf_path):
        return "⚠️ 错误：未找到 data/员工手册测试版.pdf，请检查路径。"
        
    try:
        # 1. 检索阶段
        docs = global_retriever.invoke(question)
        
        # 2. 提取阶段（获取内容及 Metadata 中的页码信息）
        sources_info = []
        context_text = ""
        for i, doc in enumerate(docs):
            page_num = doc.metadata.get("page", 0) + 1 
            context_text += f"[片段{i+1}]: {doc.page_content}\n"
            sources_info.append(f"《员工手册测试版.pdf》第 {page_num} 页")
            
        sources_info = list(set(sources_info))

        # 3. 生成阶段
        llm = ChatOpenAI(
            model="deepseek-chat", 
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0.1
        )
        
        template = """你是一个严谨的企业人事HR大管家。请完全基于【参考文档】回答员工的问题。
        如果文档中没有相关信息，请诚实回答无法找到相关规定。
        
        【参考文档】：
        {context}
        
        员工提问：{question}
        """
        prompt = ChatPromptTemplate.from_template(template).format(context=context_text, question=question)
        response = llm.invoke(prompt)
        
        # 4. 组装阶段（强行拼接溯源标记返回给前端展示）
        sources_markdown = "\n".join([f" - 📄 {src}" for src in sources_info])
        final_output = f"""{response.content}

---
#### 🔍 官方规章参考依据：
{sources_markdown}
"""
        return final_output
    except Exception as e:
        return f"企业级 RAG 检索失败: {str(e)}"