import { changePasswordSchema, registerSchema, signInSchema } from "./schemas";

describe("auth schemas mirror the server rules", () => {
  it("normalise email and display name like the server", () => {
    const result = registerSchema.parse({ display_name: "  Aarav \n  Nair ", email: " Aarav@Northfield.Example ", password: "tidal-quartz-lantern" });
    expect(result).toEqual({ display_name: "Aarav Nair", email: "aarav@northfield.example", password: "tidal-quartz-lantern" });
  });

  it.each([
    [{ display_name: "", email: "a@b.example", password: "tidal-quartz-lantern" }, "display_name", "Enter your name."],
    [{ display_name: "x".repeat(61), email: "a@b.example", password: "tidal-quartz-lantern" }, "display_name", "Use at most 60 characters."],
    [{ display_name: "A", email: "not-an-email", password: "tidal-quartz-lantern" }, "email", "Enter a valid email address."],
    [{ display_name: "A", email: "a@b.example", password: "short" }, "password", "Use at least 10 characters."],
    [{ display_name: "A", email: "a@b.example", password: "x".repeat(129) }, "password", "Use at most 128 characters."],
  ])("rejects %j on %s", (values, field, message) => {
    const result = registerSchema.safeParse(values);
    expect(result.success).toBe(false);
    expect(result.error?.issues.find((i) => i.path[0] === field)?.message).toBe(message);
  });

  it("accepts any non-empty password for sign-in (old accounts may predate rules)", () => {
    expect(signInSchema.safeParse({ email: "a@b.example", password: "x" }).success).toBe(true);
    expect(signInSchema.safeParse({ email: "a@b.example", password: "" }).success).toBe(false);
  });

  it("requires the repeated new password to match", () => {
    const result = changePasswordSchema.safeParse({ current_password: "a", new_password: "copper-meadow-harbour", confirm_password: "copper-meadow-harbor" });
    expect(result.error?.issues[0]).toMatchObject({ path: ["confirm_password"], message: "The passwords don't match." });
  });
});
