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
  sessionId: string;
  openSidebar?: boolean;
}

type ResponsePhase =
  | "connecting"
  | "thinking"
  | "slow"
  | "working"
  | "answering"
  | "stopping"
  | null;

const GENERAL_QUICK_QUESTIONS = [
  "帮我随机起一卦，看看最近的工作机会",
  "我已经有一条卦例，想继续分析用神和动爻",
  "六爻中的世爻和应爻分别代表什么？",
];

const DIVINATION_QUICK_QUESTIONS = [
  "请为当前卦例生成一份完整的 AI 解读报告",
  "请分析当前卦例的用神与动爻",
  "这个卦对我所问的事情有哪些关键提醒？",
];

export function ChatView({
  apiBase,
  userId,
  suggestionsEnabled,
  launchRequest,
  onLaunchConsumed,
  onOpenDivination,
  onNotify,
}: {
  apiBase: string;
  userId: string | null;
  suggestionsEnabled: boolean;
  launchRequest: ChatLaunchRequest | null;
  onLaunchConsumed: (token: number) => void;
  onOpenDivination: (id: string) => void;
  onNotify: (message: string) => void;
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [current, setCurrent] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [responsePhase, setResponsePhase] = useState<ResponsePhase>(null);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingComplete, setStreamingComplete] = useState(false);
  const [streamingTools, setStreamingTools] = useState<
    StreamingToolState[]
  >([]);
  const [streamingSuggestions, setStreamingSuggestions] = useState<string[]>(
    [],
  );
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const activeRunRef = useRef<{
    sessionId: string;
    requestId: string;
  } | null>(null);
  const handledLaunchRef = useRef<number | null>(null);
  const skipNextRestoreRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(null);
  const suggestionRequestRef = useRef(0);

  useEffect(() => {
    currentSessionIdRef.current = current?.id || null;
  }, [current?.id]);

  useEffect(() => {
    if (
      !streaming ||
      (responsePhase !== "connecting" && responsePhase !== "thinking")
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      setResponsePhase((phase) =>
        phase === "connecting" || phase === "thinking" ? "slow" : phase,
      );
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [responsePhase, streaming]);

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
      if (cancelled || !userId || launchRequest) return;
      if (skipNextRestoreRef.current) {
        skipNextRestoreRef.current = false;
        return;
      }
      await loadSessions();
    }
    void restoreSessions();
    return () => {
      cancelled = true;
    };
  }, [launchRequest, loadSessions, userId]);

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
    skipNextRestoreRef.current = true;
    // 启动请求是一次性事件。由父组件立即清除，避免本组件重新挂载时再次创建会话。
    onLaunchConsumed(launchRequest.token);
    setSidebarOpen(Boolean(launchRequest.openSidebar));
    void (async () => {
      try {
        await loadSessions(launchRequest.sessionId);
      } catch (launchError) {
        onNotify(
          launchError instanceof Error
            ? launchError.message
            : "打开追问会话失败",
        );
      }
    })();
  }, [
    apiBase,
    launchRequest,
    loadSessions,
    onLaunchConsumed,
    onNotify,
    userId,
  ]);

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
    suggestionRequestRef.current += 1;
    currentSessionIdRef.current = session.id;
    setCurrent(session);
    setSidebarOpen(false);
    setError("");
    setStreamingContent("");
    setStreamingComplete(false);
    setStreamingTools([]);
    setStreamingSuggestions([]);
    setSuggestionsLoading(false);
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
    if (event.event_type === "run_started") {
      setResponsePhase("thinking");
      return;
    }
    if (event.event_type === "text_delta" && event.content) {
      setResponsePhase("answering");
      setStreamingContent((content) => content + event.content);
      return;
    }
    if (event.event_type === "tool_call_started" && event.tool_call_id) {
      setResponsePhase("working");
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
      setResponsePhase("answering");
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
      setResponsePhase(null);
      setStreamingContent(event.content);
      setStreamingComplete(true);
      return;
    }
    if (event.event_type === "suggestions" && event.questions) {
      setStreamingSuggestions(event.questions);
      return;
    }
    if (event.event_type === "error") {
      setResponsePhase(null);
      setError(event.content || "问易助手暂时无法回答");
    }
  }

  async function stopCurrentRun() {
    const activeRun = activeRunRef.current;
    if (!userId || !activeRun || responsePhase === "stopping") return;
    setResponsePhase("stopping");
    suggestionRequestRef.current += 1;
    try {
      await liuyaoApi.cancelChatRun(
        apiBase,
        userId,
        activeRun.sessionId,
        activeRun.requestId,
      );
    } catch (cancelError) {
      setError(
        cancelError instanceof Error
          ? cancelError.message
          : "停止本次回答失败",
      );
    } finally {
      // 后端取消接口会先等待取消消息落库；此时再关闭浏览器流最稳定。
      abortRef.current?.abort();
    }
  }

  async function requestSuggestions(
    sessionId: string,
    messageId: string,
    requestToken: number,
  ) {
    if (!userId) return;
    setSuggestionsLoading(true);
    try {
      const result = await liuyaoApi.generateChatSuggestions(
        apiBase,
        userId,
        sessionId,
        messageId,
      );
      if (
        suggestionRequestRef.current !== requestToken ||
        currentSessionIdRef.current !== sessionId
      ) {
        return;
      }
      setStreamingSuggestions(result.questions);
      if (result.questions.length > 0) {
        const rows = await liuyaoApi.listChatMessages(
          apiBase,
          userId,
          sessionId,
          160,
        );
        if (
          suggestionRequestRef.current === requestToken &&
          currentSessionIdRef.current === sessionId
        ) {
          setMessages(rows);
          setStreamingSuggestions([]);
        }
      }
    } catch {
      // 追问是辅助能力；失败时保留主回答，不显示成整轮对话失败。
    } finally {
      if (suggestionRequestRef.current === requestToken) {
        setSuggestionsLoading(false);
      }
    }
  }

  async function sendMessage(message: string) {
    if (!userId || streaming) return;
    let activeSession = current;
    if (!activeSession) activeSession = await createSession();
    if (!activeSession || activeSession.status === "archived") return;
    currentSessionIdRef.current = activeSession.id;
    const suggestionRequestToken = suggestionRequestRef.current + 1;
    suggestionRequestRef.current = suggestionRequestToken;
    let completedMessageId: string | null = null;

    const controller = new AbortController();
    const requestId = crypto.randomUUID();
    abortRef.current?.abort();
    abortRef.current = controller;
    activeRunRef.current = {
      sessionId: activeSession.id,
      requestId,
    };
    setStreaming(true);
    setResponsePhase("connecting");
    setPendingUser(message);
    setStreamingContent("");
    setStreamingComplete(false);
    setStreamingTools([]);
    setStreamingSuggestions([]);
    setSuggestionsLoading(false);
    setError("");

    try {
      await liuyaoApi.streamChatMessage(
        apiBase,
        userId,
        activeSession.id,
        message,
        requestId,
        (event) => {
          handleStreamEvent(event);
          if (
            event.event_type === "message_completed" &&
            event.message_id
          ) {
            completedMessageId = event.message_id;
          }
        },
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
      setStreamingComplete(false);
      setStreamingTools([]);
      setStreamingSuggestions([]);
      setResponsePhase(null);
      setStreaming(false);
      if (abortRef.current === controller) abortRef.current = null;
      if (activeRunRef.current?.requestId === requestId) {
        activeRunRef.current = null;
      }
    }
    if (
      suggestionsEnabled &&
      completedMessageId &&
      !controller.signal.aborted
    ) {
      void requestSuggestions(
        activeSession.id,
        completedMessageId,
        suggestionRequestToken,
      );
    }
  }

  const isEmpty =
    !messagesLoading &&
    messages.length === 0 &&
    !pendingUser &&
    !streamingContent &&
    streamingTools.length === 0 &&
    streamingSuggestions.length === 0;
  const hasActiveDivination = Boolean(current?.active_divination_id);
  const quickQuestions = hasActiveDivination
    ? DIVINATION_QUICK_QUESTIONS
    : GENERAL_QUICK_QUESTIONS;

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
            <h1 title={current?.title || "问易"}>
              {current?.title || "问易"}
            </h1>
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
            <p className="eyebrow">
              {hasActiveDivination
                ? "卦象已入席 · 可直接问易"
                : "一问一答 · 由浅入深"}
            </p>
            <h2>
              {hasActiveDivination
                ? "从这份卦象，继续问下去"
                : "把想问的事，慢慢说来"}
            </h2>
            <p>
              {hasActiveDivination
                ? "当前排盘已经带入会话。你可以生成完整解读，也可以只问某个细节。"
                : "问易助手可以为你起卦排盘，也能围绕已有卦例持续分析。"}
              <br />
              {hasActiveDivination
                ? "只有明确请求完整报告时，系统才会调用解读 Agent。"
                : "每一次工具调用都会显示过程，排盘数据不会凭空编造。"}
            </p>
            <div>
              {quickQuestions.map((question) => (
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
            responsePhase={responsePhase}
            streamingComplete={streamingComplete}
            streamingTools={streamingTools}
            streamingSuggestions={streamingSuggestions}
            suggestionsLoading={suggestionsLoading}
            suggestionsDisabled={streaming}
            error={error}
            onOpenDivination={onOpenDivination}
            onSelectSuggestion={(question) => void sendMessage(question)}
          />
        )}

        <footer className="chat-input-area">
          <ChatComposer
            disabled={!userId || sessionsLoading}
            streaming={streaming}
            stopping={responsePhase === "stopping"}
            archived={current?.status === "archived"}
            onSend={sendMessage}
            onStop={() => void stopCurrentRun()}
          />
          <p>六爻解读仅供文化娱乐参考，不构成任何人生决策依据。</p>
        </footer>
      </section>
    </main>
  );
}
