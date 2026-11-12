import { useEffect } from "react";

/** Inputs that open a keyboard; checkboxes, radios, buttons and dates don't count. */
/** Long enough for a tap to finish; short enough not to be noticed. */
const RESTORE_DELAY_MS = 400;

const TYPING_INPUTS = new Set(["text", "search", "email", "url", "tel", "password", "number"]);

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) return TYPING_INPUTS.has(target.type);
  return target.isContentEditable === true;
}

/**
 * Design.md §4: "Bottom bar hidden while typing in a composer." Sets `data-typing` on <html>
 * while focus is in a field that opens the keyboard; the `typing:` variant (index.css) hides
 * the phone bar and drops the sticky save bars to the bottom edge.
 */
export function useTypingFlag(): void {
  useEffect(() => {
    const root = document.documentElement;
    const update = () => {
      if (isTypingTarget(document.activeElement)) root.dataset.typing = "";
      else delete root.dataset.typing;
    };
    // Leaving a field by tapping a button: focus moves on pointer-down, the click comes on
    // pointer-up. Bringing the bar back at once would put it under that finger, and the tap
    // would land on the bar. So it returns a moment later, if nothing typeable took focus.
    let timer: ReturnType<typeof setTimeout> | undefined;
    const later = () => {
      clearTimeout(timer);
      timer = setTimeout(update, RESTORE_DELAY_MS);
    };
    // Focus arriving can raise the flag at once; lowering it always waits (see above).
    const arrived = (event: FocusEvent) => {
      if (!isTypingTarget(event.target)) return later();
      clearTimeout(timer);
      update();
    };
    document.addEventListener("focusin", arrived);
    document.addEventListener("focusout", later);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("focusin", arrived);
      document.removeEventListener("focusout", later);
      delete root.dataset.typing;
    };
  }, []);
}
