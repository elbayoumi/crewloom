import type { Product } from "../hooks/useProducts";

export function ProductCard({ product, onAdd }: { product: Product; onAdd: (id: number) => void }) {
  return (
    <article className="card">
      <img
        src={product.image}
        width={280}
        height={180}
      />
      <h2>{product.name}</h2>
      <span className="badge">{product.tag}</span>
      <p style={{ color: "rgb(255 102 0)" }}>{product.price} ج.م</p>
      <p className="note" dangerouslySetInnerHTML={{ __html: product.note }} />
      <div className="add" onClick={() => onAdd(product.id)}>أضف إلى السلة</div>
      <img src="/seal.svg" alt="ختم الجودة" width={32} height={32} />
    </article>
  );
}
