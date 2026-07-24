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

async function responseError(response: Response) {
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
  return new Error(message);
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
    throw await responseError(response);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function streamInterpretation(
  apiBase: string,
  id: string,
  onContent: (content: string) => void,
  signal?: AbortSignal,
) {
  let response: Response;
  try {
    response = await fetch(
      `${normalizeBaseUrl(apiBase)}/divinations/${id}/interpret/stream`,
      {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        signal,
      },
    );
  } catch {
    if (signal?.aborted) throw new Error("AI 解读已取消");
    throw new Error("无法连接后端服务，请确认 API 已在 8022 端口启动");
  }

  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("当前浏览器不支持流式读取");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullContent = "";
  let completed = false;

  function consumeEvent(rawEvent: string) {
    const data = rawEvent
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
      .filter((line) => line === "data" || line.startsWith("data:"))
      .map((line) =>
        line === "data" ? "" : line.slice(5).replace(/^ /, ""),
      )
      .join("\n");

    if (data === "[DONE]") {
      completed = true;
      return;
    }
    if (data.startsWith("[ERROR]")) {
      throw new Error(data.slice("[ERROR]".length) || "AI 解读失败");
    }
    if (!data) return;

    fullContent += data;
    onContent(fullContent);
  }

  function findEventBoundary(value: string) {
    const match = /\r\n\r\n|\n\n|\r\r/.exec(value);
    return match?.index === undefined
      ? null
      : { index: match.index, length: match[0].length };
  }

  try {
    while (!completed) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = findEventBoundary(buffer);
      while (boundary) {
        consumeEvent(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary.length);
        if (completed) break;
        boundary = findEventBoundary(buffer);
      }

      if (done) break;
    }
  } catch (error) {
    if (signal?.aborted) throw new Error("AI 解读已取消");
    throw error instanceof Error ? error : new Error("AI 解读流读取失败");
  } finally {
    reader.releaseLock();
  }

  if (!completed) throw new Error("AI 解读连接意外中断，请重试");
  return fullContent;
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

  interpretStream(
    apiBase: string,
    id: string,
    onContent: (content: string) => void,
    signal?: AbortSignal,
  ) {
    return streamInterpretation(apiBase, id, onContent, signal);
  },
};
