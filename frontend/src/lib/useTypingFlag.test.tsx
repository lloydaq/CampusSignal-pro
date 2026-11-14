import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { isTypingTarget, useTypingFlag } from "./useTypingFlag";

function Fields() {
  useTypingFlag();
  return (
    <>
      <label>
        Post <textarea />
      </label>
      <label>
        Score <input type="text" />
      </label>
      <label>
        Absent <input type="checkbox" />
      </label>
      <button type="button">Save</button>
    </>
  );
}

describe("useTypingFlag", () => {
  it("flags <html> while a keyboard field has focus, not for checkboxes or buttons", async () => {
    const { unmount } = render(<Fields />);
    const root = document.documentElement;
    await userEvent.click(screen.getByLabelText("Post"));
    expect(root.dataset.typing).toBe("");
    await userEvent.click(screen.getByLabelText("Absent"));
    await waitFor(() => expect(root.dataset.typing).toBeUndefined());
    await userEvent.click(screen.getByLabelText("Score"));
    expect(root.dataset.typing).toBe("");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(root.dataset.typing).toBeUndefined());
    await userEvent.click(screen.getByLabelText("Post"));
    unmount();
    expect(root.dataset.typing).toBeUndefined();
  });

  it("knows which elements open a keyboard", () => {
    const input = (type: string) => Object.assign(document.createElement("input"), { type });
    expect(isTypingTarget(document.createElement("textarea"))).toBe(true);
    expect(["text", "email", "number", "search"].every((t) => isTypingTarget(input(t)))).toBe(true);
    expect(["checkbox", "radio", "date", "submit"].some((t) => isTypingTarget(input(t)))).toBe(false);
    expect(isTypingTarget(document.createElement("button"))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
