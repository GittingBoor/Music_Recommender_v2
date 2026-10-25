import { useAccount } from "../../account/useAccount";
import { Link } from "../../router";

/** Header entry to /account: "Anmelden" when logged out, the e-mail once logged in. */
export function AccountMenu({ active }: { readonly active: boolean }) {
  const account = useAccount();
  // Nothing while loading, so the header does not flash "Anmelden" for logged-in users.
  if (account === undefined) return null;

  const tone = active ? "text-ink" : "text-ink-2";
  const base = `block underline-offset-4 hover:text-ink hover:underline ${tone}`;
  return (
    <>
      <span className="h-3 w-px shrink-0 bg-line-strong" aria-hidden="true" />
      <Link
        to="/account"
        aria-current={active ? "page" : undefined}
        title={account?.email}
        className={account
          ? `${base} min-w-0 max-w-[14rem] truncate font-mono text-2xs`
          : `${base} text-xs font-medium whitespace-nowrap`}
      >
        {account?.email ?? "Anmelden"}
      </Link>
    </>
  );
}
