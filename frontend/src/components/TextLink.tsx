import { Link, type LinkProps } from "react-router";

import { cn } from "@/lib/utils";

export function TextLink({ className, ...props }: LinkProps) {
  return <Link className={cn("font-medium text-primary underline underline-offset-4 hover:text-primary-hover", className)} {...props} />;
}
