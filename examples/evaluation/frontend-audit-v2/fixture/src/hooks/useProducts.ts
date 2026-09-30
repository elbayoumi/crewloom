import { useEffect, useState } from "react";

export type Product = { id: number; name: string; price: number; image: string; note: string; tag: string };

export function useProducts(query: string) {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/products?q=${encodeURIComponent(query)}`)
      .then((r) => r.json())
      .then((data: Product[]) => {
        setProducts(data);
        setLoading(false);
      });
  }, [query]);

  return { products, loading };
}
