/** Query keys for Manage; a change invalidates the lists it affects. */
export const manageKeys = {
  requests: ["manage", "requests"],
  members: ["manage", "members"],
  departments: ["manage", "departments"],
  invites: ["manage", "invites"],
  roster: ["manage", "roster"],
  audit: ["manage", "audit"],
} as const;
