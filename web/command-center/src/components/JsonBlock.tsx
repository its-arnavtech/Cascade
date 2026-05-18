import { Check, Copy } from "lucide-react";
import { useMemo, useState } from "react";

export function JsonBlock({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false);
  const json = useMemo(() => JSON.stringify(value ?? {}, null, 2), [value]);

  async function copyJson() {
    await navigator.clipboard?.writeText(json);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="json-shell">
      <button type="button" className="btn-icon json-copy" aria-label="Copy JSON" onClick={copyJson}>
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <pre className="json-block">{json}</pre>
    </div>
  );
}
