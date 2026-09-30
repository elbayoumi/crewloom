import { useEffect, useState } from "react";

type Product = { id: number; name: string; price: number; image: string; note: string };

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");

  useEffect(() => {
    fetch("/api/products")
      .then((r) => r.json())
      .then((data) => {
        setProducts(data);
        setLoading(false);
      });
  }, []);

  return (
    <main>
      <h1>متجر الشاي</h1>
      {loading && <p>جارٍ التحميل...</p>}
      <section className="catalog">
        {products.map((p, index) => (
          <article className="card" key={index}>
            <img src={p.image} width={320} height={200} />
            <h2>{p.name}</h2>
            <span className="price">{p.price} ج.م</span>
            <p dangerouslySetInnerHTML={{ __html: p.note }} />
            <button className="icon-btn" onClick={() => console.log("add", p.id)}></button>
          </article>
        ))}
      </section>
      <section className="safe-grid">
        <img src="/logo.png" alt="شعار متجر الشاي" />
      </section>
      <form onSubmit={(e) => e.preventDefault()}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="بريدك" />
        <button type="submit" style={{ background: "#ff6600", color: "#fff" }}>اشترك</button>
      </form>
    </main>
  );
}
