import type { Notice } from "../account/spotifyNotice";

const DOT: Readonly<Record<Notice["tone"], string>> = {
  ok:  "bg-ok",
  bad: "bg-bad",
};

/** One-line outcome message: a status dot and the text, no colour wash. */
export function NoticeLine({ notice }: { readonly notice: Notice }) {
  return (
    <p
      role={notice.tone === "bad" ? "alert" : "status"}
      className="settle flex items-start gap-2.5 border border-line bg-panel px-3 py-2.5 text-sm text-ink-2 leading-snug"
    >
      <span className={`mt-[6px] h-1.5 w-1.5 shrink-0 ${DOT[notice.tone]}`} aria-hidden="true" />
      <span className="min-w-0">{notice.text}</span>
    </p>
  );
}

/** Inline error under a form or list; `message` is already user-facing German. */
export function ErrorLine({ message }: { readonly message: string }) {
  return <NoticeLine notice={{ tone: "bad", text: message }} />;
}

/** Message of a thrown value, for the inline error lines. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
