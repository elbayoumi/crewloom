import { useState } from "react";
import { useProducts } from "./hooks/useProducts";
import { ProductCard } from "./components/ProductCard";
import { Filters } from "./components/Filters";
import { Toast } from "./components/Toast";
import { CheckoutForm } from "./components/CheckoutForm";

export default function App() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("new");
  const [toast, setToast] = useState("");
  const { products, loading } = useProducts(query);

  return (
    <main>
      <h1>متجر الشاي</h1>
      <Filters query={query} onQuery={setQuery} sort={sort} onSort={setSort} />
      {loading && <p role="status">جارٍ التحميل...</p>}
      <section className="layout" aria-label="المنتجات">
        {products.map((p, i) => (
          <ProductCard key={i} product={p} onAdd={(id) => setToast(`أضيف المنتج ${id}`)} />
        ))}
      </section>
      <section className="safe-row">
        <p className="muted">الأسعار تشمل الضريبة</p>
      </section>
      <Toast message={toast} />
      <CheckoutForm />
    </main>
  );
}
