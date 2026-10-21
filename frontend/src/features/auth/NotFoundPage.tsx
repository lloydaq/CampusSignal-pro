import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Page not found</h1>
      <p className="text-base text-muted">There's nothing at this address.</p>
      <p>
        <Link to="/" className="font-medium text-primary underline underline-offset-4 hover:text-primary-hover">
          Go to the start page
        </Link>
      </p>
    </div>
  );
}
