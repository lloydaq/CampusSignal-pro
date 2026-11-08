import { Building2, ClipboardList, GraduationCap, House, Megaphone, MessagesSquare, School, Settings2, UserRound, type LucideIcon } from "lucide-react";

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
    // Design.md §4: Academics sits third in the phone bar for students.
    if (me.capabilities.includes("academics")) items.push({ to: "/academics", label: "Academics", Icon: GraduationCap });
    items.push({ to: "/community", label: "Community", Icon: MessagesSquare });
    items.push({ to: "/issues", label: "Issues", Icon: ClipboardList });
  }
  else if (!me.capabilities.includes("platform")) items.push({ to: "/join", label: "Join your college", Icon: School });
  if (me.capabilities.includes("platform")) items.push({ to: "/platform", label: "Platform", Icon: Building2 });
  if (me.capabilities.includes("review_memberships")) items.push({ to: "/manage", label: "Manage", Icon: Settings2 });
  items.push({ to: "/account", label: "Account", Icon: UserRound });
  return items;
}

/** The phone's bottom bar holds four sections; the rest go in a "More" sheet (owner, 2026-10-31:
 * Home · Notices · Community · Issues · More). Short lists fit as they are. */
export const BAR_SIZE = 4;

export function splitForBar(items: NavItem[]): { bar: NavItem[]; more: NavItem[] } {
  if (items.length <= BAR_SIZE + 1) return { bar: items, more: [] };
  return { bar: items.slice(0, BAR_SIZE), more: items.slice(BAR_SIZE) };
}
