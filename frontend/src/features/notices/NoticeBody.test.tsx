import { render } from "@testing-library/react";

import { NoticeBody } from "./NoticeBody";

function html(markdown: string): HTMLElement {
  return render(<NoticeBody markdown={markdown} />).container;
}

describe("notice body rendering (Rules R-2.18)", () => {
  it("renders the allowed subset", () => {
    const out = html("Exams start **Monday**, *not* Tuesday.\n\n- Bring ID\n- Arrive early\n\n1. One\n2. Two\n\nSee [the timetable](https://northfield.example/tt).");
    expect(out.querySelector("strong")?.textContent).toBe("Monday");
    expect(out.querySelector("em")?.textContent).toBe("not");
    expect(out.querySelectorAll("ul li")).toHaveLength(2);
    expect(out.querySelectorAll("ol li")).toHaveLength(2);
    const link = out.querySelector("a")!;
    expect(link.getAttribute("href")).toBe("https://northfield.example/tt");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer nofollow");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("never renders raw HTML", () => {
    const out = html('Hello <script>alert(1)</script> <img src=x onerror="alert(2)"> <b>bold</b>\n\n<div onclick="x()">block</div>');
    expect(out.querySelector("script, img, b, div[onclick], [onerror], [onclick]")).toBeNull();
    expect(out.innerHTML).not.toMatch(/onerror|onclick|<script/i);
  });

  it.each(["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "vbscript:msgbox(1)"])(
    "drops a dangerous link target (%s) but keeps the text",
    (target) => {
      const out = html(`[click me](${target})`);
      expect(out.textContent).toContain("click me");
      const link = out.querySelector("a");
      expect(link?.getAttribute("href") ?? null).toBeNull();
    },
  );

  it("keeps mailto links", () => {
    expect(html("[Write to us](mailto:office@northfield.example)").querySelector("a")?.getAttribute("href")).toBe("mailto:office@northfield.example");
  });

  it("turns elements outside the subset into their text", () => {
    const out = html("# Big heading\n\n![logo](https://x.example/a.png)\n\n> quoted\n\n`code`\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    expect(out.querySelector("h1, img, blockquote, code, hr, table")).toBeNull();
    expect(out.textContent).toContain("Big heading");
    expect(out.textContent).toContain("quoted");
  });
});
