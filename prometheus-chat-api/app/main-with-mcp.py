import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import openai

# --- Load environment variables
load_dotenv()

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090/api/v1/query")
MCP_URL = os.getenv("MCP_URL", "http://localhost:9876/.well-known/model-context")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")  # Set to your OpenAI key or "ollama" for local
LLM_MODEL = os.getenv("LLM_MODEL", "llama3")      # "gpt-4o" for OpenAI, "llama3" or other for Ollama
LLM_BASE_URL = os.getenv("LLM_BASE_URL", None)    # If using Ollama, e.g. "http://localhost:11434/v1"

# --- Setup FastAPI app
app = FastAPI(
    title="Prometheus Chat API",
    description="Ask Prometheus questions in natural language, powered by LLMs and Prometheus MCP.",
    version="3.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models
class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    promql: str
    result: object
    answer: str

# --- LLM Client: Supports OpenAI and Ollama
def get_llm_client():
    kwargs = {"api_key": LLM_API_KEY}
    if LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL
    return openai.OpenAI(**kwargs)

client = get_llm_client()

# --- MCP Context fetch
def get_prometheus_mcp_context():
    try:
        resp = requests.get(MCP_URL, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Warning: Could not fetch MCP context: {e}")
        return {}

@app.post("/ask", response_model=QueryResponse)
def ask_prometheus(req: QueryRequest):
    # 1. Get MCP context (metrics, labels, possible values)
    context = get_prometheus_mcp_context()
    metrics = [m["name"] for m in context.get("metrics", [])] if context else []
    labels = context.get("labels", []) if context else []
    metric_list_text = "\n".join(f"- {m}" for m in metrics[:40]) if metrics else "(no metrics found)"
    label_lines = []
    for label in labels[:15]:
        name = label.get("name")
        values = label.get("values", [])
        line = f"- {name}: {', '.join(values[:8])}{'...' if len(values) > 8 else ''}"
        label_lines.append(line)
    label_list_text = "\n".join(label_lines) if label_lines else "(no labels found)"

    # 2. LLM: NL -> PromQL, with full context
    prompt1 = (
        "You are an expert in Prometheus and PromQL.\n"
        "Here are the available Prometheus metrics in this system:\n"
        f"{metric_list_text}\n\n"
        "Here are the available label keys and some example values:\n"
        f"{label_list_text}\n\n"
        "Given all this context, write only the most appropriate PromQL query (no explanation, no formatting) to answer this question:\n"
        f"Question: {req.question}"
    )
    try:
        resp1 = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt1}],
            max_tokens=128,
            temperature=0.0,
        )
        promql = resp1.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API error (PromQL generation): {e}")

    # 3. Query Prometheus
    try:
        prometheus_resp = requests.get(PROMETHEUS_URL, params={"query": promql}, timeout=10)
        prometheus_resp.raise_for_status()
        prometheus_json = prometheus_resp.json()
        result = prometheus_json.get("data", {}).get("result", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prometheus query error: {e}")

    # 4. Truncate large results for the LLM
    MAX_RESULTS = 40
    short_result = result
    truncated = False
    if isinstance(result, list) and len(result) > MAX_RESULTS:
        short_result = result[:MAX_RESULTS]
        truncated = True

    # 5. LLM: Result -> Friendly Answer
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
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt2}],
            max_tokens=256,
            temperature=0.2,
        )
        chat_response = resp2.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API error (answer): {e}")

    return QueryResponse(
        question=req.question,
        promql=promql,
        result=result,
        answer=chat_response
    )
