"use client";

import type { ChatSession } from "../../types";

function relativeTime(value: string) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function ChatSessionList({
  sessions,
  currentId,
  loading,
  open,
  onClose,
  onCreate,
  onSelect,
  onArchive,
  onDelete,
}: {
  sessions: ChatSession[];
  currentId: string | null;
  loading: boolean;
  open: boolean;
  onClose: () => void;
  onCreate: () => void;
  onSelect: (session: ChatSession) => void;
  onArchive: (session: ChatSession) => void;
  onDelete: (session: ChatSession) => void;
}) {
  return (
    <>
      {open && (
        <button
          className="chat-sidebar-scrim"
          type="button"
          onClick={onClose}
          aria-label="关闭会话列表"
        />
      )}
      <aside className={`chat-sidebar ${open ? "open" : ""}`}>
        <header>
          <div>
            <span>会话</span>
            <strong>问易簿</strong>
          </div>
          <button type="button" onClick={onCreate}>＋ 新问</button>
        </header>

        <div className="chat-session-list">
          {loading ? (
            <p className="chat-session-empty">正在展开问易簿…</p>
          ) : sessions.length ? (
            sessions.map((session) => (
              <article
                className={session.id === currentId ? "active" : ""}
                key={session.id}
              >
                <button
                  type="button"
                  className="chat-session-main"
                  onClick={() => onSelect(session)}
                >
                  <strong>{session.title || "未题名会话"}</strong>
                  <span>
                    {session.active_divination_id
                      ? `卦例 ${session.active_divination_id.slice(0, 8)}`
                      : "自由问答"}
                  </span>
                  <small>{relativeTime(session.last_message_at)}</small>
                </button>
                <div className="chat-session-actions">
                  <button
                    type="button"
                    onClick={() => onArchive(session)}
                    title={session.status === "active" ? "归档" : "恢复"}
                  >
                    {session.status === "active" ? "收" : "启"}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(session)}
                    title="删除"
                  >
                    删
                  </button>
                </div>
              </article>
            ))
          ) : (
            <p className="chat-session-empty">
              还没有会话
              <small>从一个问题开始，或在卦例中继续追问</small>
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
