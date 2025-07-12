import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import openai
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090/api/v1/query")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not OPENAI_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment.")

app = FastAPI(
    title="Prometheus Chat API",
    description="Ask Prometheus questions in natural language.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    promql: str
    result: object
    answer: str

# OpenAI client (v1+)
client = openai.OpenAI(api_key=OPENAI_KEY)

@app.post("/ask", response_model=QueryResponse)
def ask_prometheus(req: QueryRequest):
    # 1. LLM: NL -> PromQL
    prompt1 = (
        "You are an expert in Prometheus and PromQL. "
        "Given the following natural language question, write only the PromQL query (no explanation, no formatting):\n\n"
        f"Question: {req.question}"
    )
    try:
        resp1 = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt1}],
            max_tokens=128,
            temperature=0.0,
        )
        promql = resp1.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error (PromQL generation): {e}")

    # 2. Query Prometheus
    try:
        prometheus_resp = requests.get(PROMETHEUS_URL, params={"query": promql}, timeout=10)
        prometheus_resp.raise_for_status()
        prometheus_json = prometheus_resp.json()
        result = prometheus_json.get("data", {}).get("result", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prometheus query error: {e}")

    # Truncate large results for the LLM
    MAX_RESULTS = 50
    short_result = result
    truncated = False
    if isinstance(result, list) and len(result) > MAX_RESULTS:
        short_result = result[:MAX_RESULTS]
        truncated = True

    # 3. LLM: Result -> Friendly Answer
    prompt2 = (
        f"User's Question: {req.question}\n"
        f"PromQL Query Used: {promql}\n"
        f"Raw Prometheus Result: {short_result}\n"
    )
    if truncated:
        prompt2 += (
            f"(Note: Only the first {MAX_RESULTS} results shown. Summarize or mention this in your answer if relevant.)\n"
        )
    prompt2 += (
        "Please provide a concise, human-friendly answer. "
        "Summarize what matters for the question, explain or list values in plain language, and do not show PromQL or code."
    )

    try:
        resp2 = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt2}],
            max_tokens=256,
            temperature=0.2,
        )
        chat_response = resp2.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error (answer): {e}")

    return QueryResponse(
        question=req.question,
        promql=promql,
        result=result,
        answer=chat_response
    )
