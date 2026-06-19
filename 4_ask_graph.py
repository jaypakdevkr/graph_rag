import os

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")

graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI"),
    username=os.getenv("NEO4J_USERNAME"),
    password=os.getenv("NEO4J_PASSWORD"),
    database="neo4j",
)

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)

chain = GraphCypherQAChain.from_llm(
    llm=llm,
    graph=graph,
    # verbose=True이면 생성된 Cypher와 조회 결과를 터미널에 출력
    verbose=True,
    # validate_cypher=True는 생성된 Cypher가 스키마와 맞는지 일부 검증
    validate_cypher=True,
    #"LLM이 DB 쿼리를 실행한다"는 위험을 이해하고 허용한다는 표시
    allow_dangerous_requests=True,
)

print("Graph schema:")
print(graph.schema)

questions = [
    "김민수와 보안팀은 어떤 관계야?",
]

for question in questions:
    print("\n질문:", question)
    result = chain.invoke({"query": question})
    print("답변:", result["result"])
