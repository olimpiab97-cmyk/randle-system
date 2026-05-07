import React, { useEffect, useState } from "react";

export default function TradeManagerDashboardV1() {
  const [text, setText] = useState("Loading...");

  useEffect(() => {
    const run = async () => {
      try {
        const res = await fetch("http://127.0.0.1:7001/trades");
        const data = await res.json();
        setText(JSON.stringify(data, null, 2));
      } catch (err) {
        setText("FETCH ERROR: " + err.message);
      }
    };

    run();
  }, []);

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
      <h1>Live TM Test</h1>
      <pre style={{ whiteSpace: "pre-wrap" }}>{text}</pre>
    </div>
  );
}