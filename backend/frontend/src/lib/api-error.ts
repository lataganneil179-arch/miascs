/**
 * The backend now returns:
 *  - 422 with `detail` as an ARRAY of { loc, msg } (field validation)
 *  - 429 with a Retry-After header (too many login attempts)
 *  - 409 for duplicate accounts / already-booked time slots
 * Use toApiError() in your fetch wrapper so every screen shows a readable message.
 */

type ValidationItem = { loc?: (string | number)[]; msg?: string };

export class ApiError extends Error {
  status: number;
  retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function getErrorMessage(
  payload: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const messages = (detail as ValidationItem[])
      .map((item) => {
        const field = item.loc?.filter((part) => part !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return messages.join("\n");
  }

  return fallback;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // non-JSON error body; fall back to the default message
  }

  const retryAfter = Number(response.headers.get("Retry-After")) || undefined;
  const message =
    response.status === 429
      ? `Too many attempts. Try again in ${Math.ceil((retryAfter ?? 900) / 60)} minute(s).`
      : getErrorMessage(body);

  return new ApiError(response.status, message, retryAfter);
}
