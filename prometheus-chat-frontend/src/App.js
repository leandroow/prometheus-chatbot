import React, { useState } from "react";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/ask";

function App() {
  const [messages, setMessages] = useState([
    {
      role: "system",
      content: "Welcome! Ask me anything about your Prometheus cluster.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    setMessages((msgs) => [...msgs, { role: "user", content: input }]);
    setLoading(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: input }),
      });
      const data = await res.json();
      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: data.answer || "(No answer)",
          promql: data.promql,
          raw: data.result,
        },
      ]);
    } catch (e) {
      setMessages((msgs) => [
        ...msgs,
        {
          role: "assistant",
          content: `Error: ${e.message || e}`,
        },
      ]);
    } finally {
      setInput("");
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !loading) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ maxWidth: 700, margin: "40px auto", fontFamily: "system-ui" }}>
      <h1>Prometheus Chat</h1>
      <div style={{
        border: "1px solid #ddd",
        padding: 20,
        borderRadius: 8,
        background: "#fafbfc",
        minHeight: 400,
        marginBottom: 16,
        maxHeight: 500,
        overflowY: "auto"
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: 18,
            textAlign: msg.role === "user" ? "right" : "left"
          }}>
            <div style={{
              display: "inline-block",
              background: msg.role === "user" ? "#1976d2" : "#e6ecf5",
              color: msg.role === "user" ? "#fff" : "#222",
              borderRadius: 16,
              padding: "10px 18px",
              maxWidth: "90%",
              wordBreak: "break-word"
            }}>
              <strong>
                {msg.role === "user" ? "You: " : msg.role === "assistant" ? "Prometheus: " : ""}
              </strong>
              <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
              {msg.promql &&
                <div style={{ fontSize: 12, marginTop: 8, color: "#888" }}>
                  <strong>PromQL:</strong> <code>{msg.promql}</code>
                </div>
              }
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ color: "#888", fontStyle: "italic" }}>
            Prometheus is thinking...
          </div>
        )}
      </div>
      <form onSubmit={e => { e.preventDefault(); handleSend(); }}>
        <textarea
          rows={2}
          style={{
            width: "100%",
            resize: "vertical",
            fontSize: 16,
            borderRadius: 8,
            border: "1px solid #ddd",
            padding: 10,
            boxSizing: "border-box"
          }}
          placeholder="Ask Prometheus a question..."
          value={input}
          disabled={loading}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="submit"
          style={{
            marginTop: 8,
            float: "right",
            background: "#1976d2",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "10px 24px",
            fontSize: 16,
            cursor: loading ? "not-allowed" : "pointer"
          }}
          disabled={loading}
        >
          Send
        </button>
      </form>
      <div style={{ marginTop: 24, color: "#888", fontSize: 13 }}>
        <strong>Note:</strong> This is a demo chat for Prometheus LLM API. Data is not stored.
      </div>
    </div>
  );
}

export default App;
