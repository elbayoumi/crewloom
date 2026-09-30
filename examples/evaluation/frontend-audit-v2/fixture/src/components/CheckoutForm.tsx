import { useState } from "react";

export function CheckoutForm() {
  const [card, setCard] = useState("");
  const [error, setError] = useState("");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (card.replace(/\s/g, "").length !== 16) {
      setError("رقم البطاقة غير صحيح");
      return;
    }
    console.log("checkout", { card });
  }

  return (
    <form onSubmit={submit} className="card">
      <label htmlFor="card">رقم البطاقة</label>
      <input id="card" inputMode="numeric" value={card} onChange={(e) => setCard(e.target.value)} />
      {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
      <button type="submit">ادفع</button>
      <button type="button" onClick={() => setCard("")}><svg width="16" height="16" viewBox="0 0 16 16"><path d="M2 2l12 12M14 2L2 14" stroke="currentColor" /></svg></button>
    </form>
  );
}
