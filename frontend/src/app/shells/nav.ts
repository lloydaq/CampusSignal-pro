import { Building2, House, Megaphone, School, Settings2, UserRound, type LucideIcon } from "lucide-react";

import type { Me } from "@/features/auth/api";

export interface NavItem {
  to: string;
  label: string;
  Icon: LucideIcon;
}

/** Only sections the account can use (Design.md §4); more arrive with their phases. */
export function navItems(me: Me): NavItem[] {
  const items: NavItem[] = [];
  if (me.capabilities.includes("campus")) {
    items.push({ to: "/home", label: "Home", Icon: House });
    items.push({ to: "/notices", label: "Notices", Icon: Megaphone });
  }
  else if (!me.capabilities.includes("platform")) items.push({ to: "/join", label: "Join your college", Icon: School });
  if (me.capabilities.includes("platform")) items.push({ to: "/platform", label: "Platform", Icon: Building2 });
  if (me.capabilities.includes("review_memberships")) items.push({ to: "/manage", label: "Manage", Icon: Settings2 });
  items.push({ to: "/account", label: "Account", Icon: UserRound });
  return items;
}
