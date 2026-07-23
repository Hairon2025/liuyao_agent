import type {
  DivinationResponse,
  MarkdownResponse,
  QiguaRequest,
} from "./types";

export const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8022";

function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/+$/, "");
}

async function request<T>(
  apiBase: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${normalizeBaseUrl(apiBase)}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new Error("无法连接后端服务，请确认 API 已在 8022 端口启动");
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((item) => item.msg).filter(Boolean).join("；");
      }
    } catch {
      // Keep the status-based fallback when the body is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const liuyaoApi = {
  health(apiBase: string) {
    return request<{ status: string }>(apiBase, "/health");
  },

  create(apiBase: string, payload: QiguaRequest) {
    return request<DivinationResponse>(apiBase, "/divinations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  list(apiBase: string) {
    return request<string[]>(apiBase, "/divinations");
  },

  get(apiBase: string, id: string) {
    return request<DivinationResponse>(apiBase, `/divinations/${id}`);
  },

  remove(apiBase: string, id: string) {
    return request<void>(apiBase, `/divinations/${id}`, {
      method: "DELETE",
    });
  },

  generateMarkdown(apiBase: string, id: string) {
    return request<MarkdownResponse>(
      apiBase,
      `/divinations/${id}/markdown`,
      { method: "POST" },
    );
  },

  getMarkdown(apiBase: string, id: string) {
    return request<MarkdownResponse>(
      apiBase,
      `/divinations/${id}/markdown`,
    );
  },

  interpret(apiBase: string, id: string) {
    return request<DivinationResponse>(
      apiBase,
      `/divinations/${id}/interpret`,
      { method: "POST" },
    );
  },
};
