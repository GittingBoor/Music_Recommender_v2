import { useId } from "react";
import type { InputHTMLAttributes } from "react";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "className"> {
  readonly label: string;
  readonly hint?: string;
}

/** Labelled input: mono label above, optional hint below. */
export function TextField({ label, hint, ...input }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="t-label block">{label}</label>
      <input id={id} aria-describedby={hint ? hintId : undefined} className="field w-full" {...input} />
      {hint && <p id={hintId} className="font-mono text-2xs text-ink-3">{hint}</p>}
    </div>
  );
}
