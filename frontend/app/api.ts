import type {
  ChatEvent,
  ChatMessage,
  ChatSession,
  ChatSessionOpenResult,
  ChatSessionStatus,
  ChatSuggestionsResponse,
  DivinationResponse,
  AuthResponse,
  MarkdownResponse,
  QiguaRequest,
  UserLLMSettings,
  UserLLMSettingsInput,
} from "./types";

export const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8022";

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
      credentials: "include",
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
  _userId: string,
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
        credentials: "include",
        headers: {
          Accept: "text/event-stream",
        },
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

async function streamChatEvents(
  apiBase: string,
  _userId: string,
  sessionId: string,
  message: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
) {
  let response: Response;
  try {
    response = await fetch(
      `${normalizeBaseUrl(apiBase)}/chat/sessions/${sessionId}/messages/stream`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
        signal,
      },
    );
  } catch {
    if (signal?.aborted) throw new Error("已停止生成");
    throw new Error("无法连接后端服务，请确认 API 已在 8022 端口启动");
  }

  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new Error("当前浏览器不支持流式读取");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  function consumeEvent(rawEvent: string) {
    const normalized = rawEvent
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n");
    const lines = normalized.split("\n");
    const eventName =
      lines
        .find((line) => line.startsWith("event:"))
        ?.slice(6)
        .trim() || "message";
    const data = lines
      .filter((line) => line === "data" || line.startsWith("data:"))
      .map((line) =>
        line === "data" ? "" : line.slice(5).replace(/^ /, ""),
      )
      .join("\n");

    if (eventName === "done" || data === "[DONE]") {
      completed = true;
      return;
    }
    if (!data) return;
    try {
      onEvent(JSON.parse(data) as ChatEvent);
    } catch {
      throw new Error("聊天服务返回了无法解析的事件");
    }
  }

  function findBoundary(value: string) {
    const match = /\r\n\r\n|\n\n|\r\r/.exec(value);
    return match?.index === undefined
      ? null
      : { index: match.index, length: match[0].length };
  }

  try {
    while (!completed) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary = findBoundary(buffer);
      while (boundary) {
        consumeEvent(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary.length);
        if (completed) break;
        boundary = findBoundary(buffer);
      }
      if (done) break;
    }
  } catch (error) {
    if (signal?.aborted) throw new Error("已停止生成");
    throw error instanceof Error ? error : new Error("聊天流读取失败");
  } finally {
    reader.releaseLock();
  }

  if (!completed) throw new Error("聊天连接意外中断，请重试");
}

export const liuyaoApi = {
  health(apiBase: string) {
    return request<{ status: string }>(apiBase, "/health");
  },

  createGuest(apiBase: string) {
    return request<AuthResponse>(apiBase, "/auth/guests", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  getCurrentUser(apiBase: string) {
    return request<AuthResponse>(apiBase, "/auth/me");
  },

  register(
    apiBase: string,
    payload: { username: string; password: string; display_name?: string },
  ) {
    return request<AuthResponse>(apiBase, "/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  login(apiBase: string, payload: { username: string; password: string }) {
    return request<AuthResponse>(apiBase, "/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  logout(apiBase: string) {
    return request<void>(apiBase, "/auth/logout", { method: "POST" });
  },

  getLLMSettings(apiBase: string) {
    return request<UserLLMSettings | null>(
      apiBase,
      "/users/me/llm-settings",
    );
  },

  saveLLMSettings(apiBase: string, payload: UserLLMSettingsInput) {
    return request<UserLLMSettings>(apiBase, "/users/me/llm-settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  testLLMSettings(apiBase: string) {
    return request<{ success: boolean; message: string }>(
      apiBase,
      "/users/me/llm-settings/test",
      { method: "POST" },
    );
  },

  deleteLLMSettings(apiBase: string) {
    return request<void>(apiBase, "/users/me/llm-settings", {
      method: "DELETE",
    });
  },

  create(apiBase: string, _userId: string, payload: QiguaRequest) {
    return request<DivinationResponse>(apiBase, "/divinations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  list(apiBase: string, _userId: string) {
    void _userId;
    return request<string[]>(apiBase, "/divinations");
  },

  get(apiBase: string, _userId: string, id: string) {
    return request<DivinationResponse>(apiBase, `/divinations/${id}`);
  },

  remove(apiBase: string, _userId: string, id: string) {
    return request<void>(apiBase, `/divinations/${id}`, {
      method: "DELETE",
    });
  },

  generateMarkdown(apiBase: string, _userId: string, id: string) {
    return request<MarkdownResponse>(
      apiBase,
      `/divinations/${id}/markdown`,
      {
        method: "POST",
      },
    );
  },

  getMarkdown(apiBase: string, _userId: string, id: string) {
    return request<MarkdownResponse>(
      apiBase,
      `/divinations/${id}/markdown`,
      {},
    );
  },

  interpretStream(
    apiBase: string,
    _userId: string,
    id: string,
    onContent: (content: string) => void,
    signal?: AbortSignal,
  ) {
    return streamInterpretation(apiBase, _userId, id, onContent, signal);
  },

  createChatSession(
    apiBase: string,
    _userId: string,
    payload: {
      title?: string;
      active_divination_id?: string;
    } = {},
  ) {
    return request<ChatSession>(apiBase, "/chat/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  openDivinationChatSession(
    apiBase: string,
    _userId: string,
    payload: {
      divination_id: string;
      mode?: "reuse_latest" | "create_new";
      title?: string;
    },
  ) {
    return request<ChatSessionOpenResult>(
      apiBase,
      "/chat/sessions/open",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },

  listDivinationChatSessions(
    apiBase: string,
    _userId: string,
    divinationId: string,
  ) {
    const query = new URLSearchParams({
      divination_id: divinationId,
      limit: "100",
    });
    return request<ChatSession[]>(
      apiBase,
      `/chat/sessions?${query.toString()}`,
      {},
    );
  },

  listChatSessions(
    apiBase: string,
    _userId: string,
    status?: ChatSessionStatus,
  ) {
    const query = status ? `?status=${status}` : "";
    return request<ChatSession[]>(
      apiBase,
      `/chat/sessions${query}`,
      {},
    );
  },

  getChatSession(apiBase: string, _userId: string, sessionId: string) {
    return request<ChatSession>(
      apiBase,
      `/chat/sessions/${sessionId}`,
      {},
    );
  },

  updateChatSession(
    apiBase: string,
    _userId: string,
    sessionId: string,
    payload: {
      title?: string | null;
      status?: ChatSessionStatus;
      active_divination_id?: string | null;
      model?: string | null;
    },
  ) {
    return request<ChatSession>(
      apiBase,
      `/chat/sessions/${sessionId}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
  },

  removeChatSession(apiBase: string, _userId: string, sessionId: string) {
    return request<void>(
      apiBase,
      `/chat/sessions/${sessionId}`,
      {
        method: "DELETE",
      },
    );
  },

  listChatMessages(
    apiBase: string,
    _userId: string,
    sessionId: string,
    limit = 100,
  ) {
    return request<ChatMessage[]>(
      apiBase,
      `/chat/sessions/${sessionId}/messages?recent=true&limit=${limit}`,
      {},
    );
  },

  streamChatMessage(
    apiBase: string,
    _userId: string,
    sessionId: string,
    message: string,
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
  ) {
    return streamChatEvents(
      apiBase,
      _userId,
      sessionId,
      message,
      onEvent,
      signal,
    );
  },

  generateChatSuggestions(
    apiBase: string,
    _userId: string,
    sessionId: string,
    messageId: string,
  ) {
    return request<ChatSuggestionsResponse>(
      apiBase,
      `/chat/sessions/${sessionId}/messages/${messageId}/suggestions`,
      {
        method: "POST",
      },
    );
  },
};
