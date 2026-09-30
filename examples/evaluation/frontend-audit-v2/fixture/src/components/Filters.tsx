type Props = { query: string; onQuery: (value: string) => void; sort: string; onSort: (value: string) => void };

export function Filters({ query, onQuery, sort, onSort }: Props) {
  return (
    <div className="toolbar">
      <div className="grid grid-cols-[minmax(300px,1fr)_1fr] gap-4">
        <label htmlFor="q">بحث</label>
        <input id="q" value={query} onChange={(e) => onQuery(e.target.value)} />
        <select value={sort} onChange={(e) => onSort(e.target.value)}>
          <option value="new">الأحدث</option>
          <option value="price">السعر</option>
        </select>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,1fr)]">
        <button className="bg-[#ff6600] px-4 py-2" type="button" onClick={() => onQuery("")}>مسح</button>
      </div>
    </div>
  );
}
