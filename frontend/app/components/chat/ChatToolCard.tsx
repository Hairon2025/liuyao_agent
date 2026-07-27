"use client";

import type { ChatMessage, ChatToolResult } from "../../types";

export interface StreamingToolState {
  id: string;
  name: string;
  status: "running" | "completed" | "failed";
  result?: ChatToolResult;
}

const TOOL_LABELS: Record<string, { mark: string; running: string }> = {
  create_divination: { mark: "卦", running: "正在起卦排盘" },
  get_divination: { mark: "阅", running: "正在调取卦例" },
  list_divinations: { mark: "册", running: "正在翻阅历史卦例" },
};

function resultFromMessage(message: ChatMessage): ChatToolResult | null {
  if (!message.payload || typeof message.payload !== "object") return null;
  const payload = message.payload as Partial<ChatToolResult>;
  if (typeof payload.success !== "boolean") return null;
  return payload as ChatToolResult;
}

export function ChatToolCard({
  state,
  message,
  onOpenDivination,
}: {
  state?: StreamingToolState;
  message?: ChatMessage;
  onOpenDivination: (id: string) => void;
}) {
  const name = state?.name || message?.tool_name || "unknown";
  const meta = TOOL_LABELS[name] || {
    mark: "术",
    running: "正在调用工具",
  };
  const result = state?.result || (message ? resultFromMessage(message) : null);
  const status =
    state?.status ||
    (result?.success === false ? "failed" : "completed");
  const data =
    result?.data && typeof result.data === "object"
      ? (result.data as Record<string, unknown>)
      : null;
  const divinationId =
    typeof data?.divination_id === "string"
      ? data.divination_id
      : message?.divination_id;
  const display =
    status === "running"
      ? meta.running
      : result?.display_content ||
        (status === "failed" ? "工具执行未完成" : "工具执行完成");

  return (
    <aside className={`chat-tool-card ${status}`} aria-live="polite">
      <span className="chat-tool-mark">{meta.mark}</span>
      <div>
        <strong>{display}</strong>
        <small>
          {status === "running"
            ? "请稍候…"
            : status === "failed"
              ? result?.model_content || "可以调整问题后重试"
              : "已将结果交给问易助手继续分析"}
        </small>
      </div>
      {divinationId && status === "completed" && (
        <button
          type="button"
          onClick={() => onOpenDivination(divinationId)}
        >
          查看排盘
        </button>
      )}
      {status === "running" && <i aria-hidden="true" />}
    </aside>
  );
}
