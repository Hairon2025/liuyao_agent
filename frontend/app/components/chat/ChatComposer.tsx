"use client";

import { useState } from "react";

export function ChatComposer({
  disabled,
  streaming,
  stopping,
  archived,
  onSend,
  onStop,
}: {
  disabled: boolean;
  streaming: boolean;
  stopping: boolean;
  archived: boolean;
  onSend: (message: string) => Promise<void>;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");

  async function submit() {
    const message = value.trim();
    if (!message || disabled || streaming || archived) return;
    setValue("");
    await onSend(message);
  }

  return (
    <div className="chat-composer">
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void submit();
          }
        }}
        placeholder={
          archived
            ? "该会话已归档，恢复后可以继续问"
            : "写下你的问题；Enter 发送，Shift + Enter 换行"
        }
        maxLength={10000}
        disabled={disabled || archived}
        rows={2}
      />
      <div>
        <small>{value.length} / 10000</small>
        {streaming ? (
          <button type="button" className="stop" onClick={onStop} disabled={stopping}>
            {stopping ? "正在停止…" : "停止"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={disabled || archived || !value.trim()}
          >
            发送 <span>↑</span>
          </button>
        )}
      </div>
    </div>
  );
}
