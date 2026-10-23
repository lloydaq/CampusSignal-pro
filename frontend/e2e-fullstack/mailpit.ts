import { expect, type APIRequestContext } from "@playwright/test";

/** Reads emails caught by Mailpit through its HTTP API (https://mailpit.axllent.org/docs/api-v1/). */

const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://127.0.0.1:8025";

interface Summary {
  ID: string;
  Subject: string;
}

async function search(request: APIRequestContext, to: string): Promise<Summary[]> {
  const response = await request.get(`${MAILPIT_URL}/api/v1/search`, { params: { query: `to:"${to}"` } });
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { messages: Summary[] }).messages;
}

/** Count of emails to `to` whose subject contains `subject`. */
export async function countEmails(request: APIRequestContext, to: string, subject: string): Promise<number> {
  return (await search(request, to)).filter((m) => m.Subject.includes(subject)).length;
}

/**
 * The plain-text body of the newest email to `to` with `subject`, waiting for it to arrive
 * (the API sends mail in a background task after the response). `after` is the number of
 * matching emails that existed before, so an older email is never mistaken for the new one.
 */
export async function waitForEmail(request: APIRequestContext, to: string, subject: string, after = 0): Promise<string> {
  let id: string | undefined;
  await expect
    .poll(
      async () => {
        const matching = (await search(request, to)).filter((m) => m.Subject.includes(subject));
        id = matching.length > after ? matching[0]?.ID : undefined; // newest first
        return id;
      },
      { message: `email "${subject}" to ${to}`, timeout: 15_000 },
    )
    .toBeTruthy();
  const response = await request.get(`${MAILPIT_URL}/api/v1/message/${id}`);
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { Text: string }).Text;
}

/** The first link in an email body that starts with `prefix`. */
export function linkIn(text: string, prefix: string): string {
  const match = text.split(/\s+/).find((word) => word.startsWith(prefix));
  if (!match) throw new Error(`no ${prefix} link in the email`);
  return match;
}
