import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import SimpleJsonOutputParser

load_dotenv()

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("OPENAI_API_KEY"), 
    base_url=os.getenv("OPENAI_API_BASE"),
    temperature=0.3
)

def analyze_resume(resume_text: str, jd_text: str) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个互联网大厂资深 HRBP。
        请仔细对比提供的【候选人简历】和【职位描述（JD）】。
        
        你必须输出一个标准的 JSON 对象，包含以下三个字段：
        - score: 0-100的匹配度整数分数。
        - pros: 数组格式，列出高度匹配的硬核优势。
        - cons: 数组格式，列出简历中明显欠缺或待提升的能力。
        """),
        ("user", "【职位描述】\n{jd}\n\n【候选人简历】\n{resume}")
    ])
    
    chain = prompt | llm | SimpleJsonOutputParser()
    
    try:
        response = chain.invoke({"jd": jd_text, "resume": resume_text})
        return response
    except Exception as e:
        return {"score": 0, "pros": ["系统解析失败"], "cons": [str(e)]}