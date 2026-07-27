"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { liuyaoApi } from "../../api";
import type {
  ChatEvent,
  ChatMessage,
  ChatSession,
} from "../../types";
import { ChatComposer } from "./ChatComposer";
import { ChatMessageList } from "./ChatMessageList";
import { ChatSessionList } from "./ChatSessionList";
import type { StreamingToolState } from "./ChatToolCard";

export interface ChatLaunchRequest {
  token: number;
  divinationId: string;
  title: string;
}

const QUICK_QUESTIONS = [
  "帮我随机起一卦，看看最近的工作机会",
  "我已经有一条卦例，想继续分析用神和动爻",
  "六爻中的世爻和应爻分别代表什么？",
];

export function ChatView({
  apiBase,
  userId,
  launchRequest,
  onOpenDivination,
  onNotify,
}: {
  apiBase: string;
  userId: string | null;
  launchRequest: ChatLaunchRequest | null;
  onOpenDivination: (id: string) => void;
  onNotify: (message: string) => void;
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [current, setCurrent] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingTools, setStreamingTools] = useState<
    StreamingToolState[]
  >([]);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const handledLaunchRef = useRef<number | null>(null);

  const loadMessages = useCallback(
    async (session: ChatSession) => {
      if (!userId) return;
      setMessagesLoading(true);
      try {
        const rows = await liuyaoApi.listChatMessages(
          apiBase,
          userId,
          session.id,
          160,
        );
        setMessages(rows);
      } catch (loadError) {
        onNotify(
          loadError instanceof Error
            ? loadError.message
            : "会话消息加载失败",
        );
      } finally {
        setMessagesLoading(false);
      }
    },
    [apiBase, onNotify, userId],
  );

  const loadSessions = useCallback(
    async (preferredId?: string) => {
      if (!userId) return [];
      setSessionsLoading(true);
      try {
        const rows = await liuyaoApi.listChatSessions(apiBase, userId);
        setSessions(rows);
        const selected =
          rows.find((item) => item.id === preferredId) ||
          rows[0] ||
          null;
        setCurrent(selected);
        if (selected) {
          await loadMessages(selected);
        } else if (!selected) {
          setMessages([]);
        }
        return rows;
      } catch (loadError) {
        onNotify(
          loadError instanceof Error
            ? loadError.message
            : "会话列表加载失败",
        );
        return [];
      } finally {
        setSessionsLoading(false);
      }
    },
    [apiBase, loadMessages, onNotify, userId],
  );

  useEffect(() => {
    let cancelled = false;
    async function restoreSessions() {
      await Promise.resolve();
      if (!cancelled && userId) await loadSessions();
    }
    void restoreSessions();
    return () => {
      cancelled = true;
    };
  }, [loadSessions, userId]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    if (
      !launchRequest ||
      !userId ||
      handledLaunchRef.current === launchRequest.token
    ) {
      return;
    }
    handledLaunchRef.current = launchRequest.token;
    void (async () => {
      try {
        const created = await liuyaoApi.createChatSession(apiBase, userId, {
          title: launchRequest.title.slice(0, 100),
          active_divination_id: launchRequest.divinationId,
        });
        setCurrent(created);
        setMessages([]);
        await loadSessions(created.id);
        onNotify("已建立卦例追问会话");
      } catch (launchError) {
        onNotify(
          launchError instanceof Error
            ? launchError.message
            : "建立追问会话失败",
        );
      }
    })();
  }, [apiBase, launchRequest, loadSessions, onNotify, userId]);

  async function createSession() {
    if (!userId) {
      onNotify("访客身份正在初始化，请稍候");
      return null;
    }
    try {
      const created = await liuyaoApi.createChatSession(apiBase, userId);
      setCurrent(created);
      setMessages([]);
      setSidebarOpen(false);
      await loadSessions(created.id);
      return created;
    } catch (createError) {
      onNotify(
        createError instanceof Error
          ? createError.message
          : "新建会话失败",
      );
      return null;
    }
  }

  async function selectSession(session: ChatSession) {
    if (streaming) return;
    setCurrent(session);
    setSidebarOpen(false);
    setError("");
    setStreamingContent("");
    setStreamingTools([]);
    await loadMessages(session);
  }

  async function toggleArchive(session: ChatSession) {
    if (!userId || streaming) return;
    try {
      const updated = await liuyaoApi.updateChatSession(
        apiBase,
        userId,
        session.id,
        { status: session.status === "active" ? "archived" : "active" },
      );
      setCurrent((value) => (value?.id === updated.id ? updated : value));
      await loadSessions(updated.id);
    } catch (archiveError) {
      onNotify(
        archiveError instanceof Error
          ? archiveError.message
          : "会话状态更新失败",
      );
    }
  }

  async function removeSession(session: ChatSession) {
    if (!userId || streaming) return;
    if (!window.confirm(`确定删除“${session.title || "未题名会话"}”吗？`)) {
      return;
    }
    try {
      await liuyaoApi.removeChatSession(apiBase, userId, session.id);
      if (current?.id === session.id) {
        setCurrent(null);
        setMessages([]);
      }
      await loadSessions();
      onNotify("会话已删除");
    } catch (removeError) {
      onNotify(
        removeError instanceof Error
          ? removeError.message
          : "删除会话失败",
      );
    }
  }

  function handleStreamEvent(event: ChatEvent) {
    if (event.event_type === "text_delta" && event.content) {
      setStreamingContent((content) => content + event.content);
      return;
    }
    if (event.event_type === "tool_call_started" && event.tool_call_id) {
      setStreamingTools((tools) => [
        ...tools.filter((tool) => tool.id !== event.tool_call_id),
        {
          id: event.tool_call_id,
          name: event.tool_name || "unknown",
          status: "running",
        },
      ]);
      return;
    }
    if (
      (event.event_type === "tool_call_completed" ||
        event.event_type === "tool_call_failed") &&
      event.tool_call_id
    ) {
      setStreamingTools((tools) =>
        tools.map((tool) =>
          tool.id === event.tool_call_id
            ? {
                ...tool,
                status:
                  event.event_type === "tool_call_completed"
                    ? "completed"
                    : "failed",
                result: event.tool_result || undefined,
              }
            : tool,
        ),
      );
      return;
    }
    if (event.event_type === "message_completed" && event.content) {
      setStreamingContent(event.content);
      return;
    }
    if (event.event_type === "error") {
      setError(event.content || "问易助手暂时无法回答");
    }
  }

  async function sendMessage(message: string) {
    if (!userId || streaming) return;
    let activeSession = current;
    if (!activeSession) activeSession = await createSession();
    if (!activeSession || activeSession.status === "archived") return;

    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;
    setStreaming(true);
    setPendingUser(message);
    setStreamingContent("");
    setStreamingTools([]);
    setError("");

    try {
      await liuyaoApi.streamChatMessage(
        apiBase,
        userId,
        activeSession.id,
        message,
        handleStreamEvent,
        controller.signal,
      );
    } catch (streamError) {
      if (!controller.signal.aborted) {
        setError(
          streamError instanceof Error
            ? streamError.message
            : "问易连接失败",
        );
      }
    } finally {
      try {
        const [updated, rows] = await Promise.all([
          liuyaoApi.getChatSession(apiBase, userId, activeSession.id),
          liuyaoApi.listChatMessages(
            apiBase,
            userId,
            activeSession.id,
            160,
          ),
        ]);
        setCurrent(updated);
        setMessages(rows);
        setSessions((items) => [
          updated,
          ...items.filter((item) => item.id !== updated.id),
        ]);
      } catch {
        // 流式错误信息已经展示，刷新失败不覆盖原始错误。
      }
      setPendingUser(null);
      setStreamingContent("");
      setStreamingTools([]);
      setStreaming(false);
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  const isEmpty =
    !messagesLoading &&
    messages.length === 0 &&
    !pendingUser &&
    !streamingContent &&
    streamingTools.length === 0;

  return (
    <main className="chat-page">
      <ChatSessionList
        sessions={sessions}
        currentId={current?.id || null}
        loading={sessionsLoading}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onCreate={() => void createSession()}
        onSelect={(session) => void selectSession(session)}
        onArchive={(session) => void toggleArchive(session)}
        onDelete={(session) => void removeSession(session)}
      />

      <section className="chat-main">
        <header className="chat-header">
          <button
            type="button"
            className="chat-menu-button"
            onClick={() => setSidebarOpen(true)}
            aria-label="打开会话列表"
          >
            ☰
          </button>
          <div>
            <span className="eyebrow">多轮问卦</span>
            <h1>{current?.title || "问易"}</h1>
            <p>
              {current?.active_divination_id
                ? `当前卦例 · ${current.active_divination_id}`
                : "可以直接提问，也可以让助手随机起卦"}
            </p>
          </div>
          <div className="chat-header-actions">
            {current?.active_divination_id && (
              <button
                type="button"
                onClick={() =>
                  onOpenDivination(current.active_divination_id as string)
                }
              >
                查看当前排盘
              </button>
            )}
            {current && (
              <button
                type="button"
                onClick={() => void toggleArchive(current)}
                disabled={streaming}
              >
                {current.status === "active" ? "归档" : "恢复"}
              </button>
            )}
          </div>
        </header>

        {isEmpty ? (
          <section className="chat-welcome">
            <span>问</span>
            <p className="eyebrow">一问一答 · 由浅入深</p>
            <h2>把想问的事，慢慢说来</h2>
            <p>
              问易助手可以为你起卦排盘，也能围绕已有卦例持续分析。
              <br />
              每一次工具调用都会显示过程，排盘数据不会凭空编造。
            </p>
            <div>
              {QUICK_QUESTIONS.map((question) => (
                <button
                  type="button"
                  key={question}
                  onClick={() => void sendMessage(question)}
                  disabled={!userId || streaming}
                >
                  {question}
                  <i>→</i>
                </button>
              ))}
            </div>
          </section>
        ) : messagesLoading ? (
          <div className="chat-loading">正在整理会话脉络…</div>
        ) : (
          <ChatMessageList
            messages={messages}
            pendingUser={pendingUser}
            streamingContent={streamingContent}
            streamingTools={streamingTools}
            error={error}
            onOpenDivination={onOpenDivination}
          />
        )}

        <footer className="chat-input-area">
          <ChatComposer
            disabled={!userId || sessionsLoading}
            streaming={streaming}
            archived={current?.status === "archived"}
            onSend={sendMessage}
            onStop={() => abortRef.current?.abort()}
          />
          <p>六爻解读仅供文化娱乐参考，不构成任何人生决策依据。</p>
        </footer>
      </section>
    </main>
  );
}
