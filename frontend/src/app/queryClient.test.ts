import { ApiError } from "@/lib/api";

import { createQueryClient } from "./queryClient";

type RetryFn = (failureCount: number, error: unknown) => boolean;

const retry = createQueryClient().getDefaultOptions().queries?.retry as RetryFn;

describe("query retry policy", () => {
  it("retries server and network errors twice", () => {
    const serverError = new ApiError(500, "internal_error", "x", null, null);
    expect(retry(0, serverError)).toBe(true);
    expect(retry(1, serverError)).toBe(true);
    expect(retry(2, serverError)).toBe(false);
    expect(retry(0, new ApiError(0, "network_error", "x", null, null))).toBe(true);
  });

  it("does not retry client errors", () => {
    expect(retry(0, new ApiError(404, "not_found", "x", null, null))).toBe(false);
    expect(retry(0, new ApiError(422, "validation_error", "x", null, null))).toBe(false);
  });
});
