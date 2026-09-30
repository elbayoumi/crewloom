import { useEffect, useState } from "react";

export function Toast({ message }: { message: string }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!message) return;
    setVisible(true);
    setTimeout(() => setVisible(false), 3000);
  }, [message]);

  return visible ? <div className="card link">{message}</div> : null;
}
