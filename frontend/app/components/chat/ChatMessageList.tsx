"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../types";
import {
  ChatToolCard,
  type StreamingToolState,
} from "./ChatToolCard";
import { SuggestedQuestions } from "./SuggestedQuestions";

function suggestionQuestions(message: ChatMessage) {
  if (
    !message.payload ||
    typeof message.payload !== "object" ||
    !("questions" in message.payload)
  ) {
    return [];
  }
  const questions = (message.payload as { questions?: unknown }).questions;
  return Array.isArray(questions)
    ? questions.filter((item): item is string => typeof item === "string")
    : [];
}

const markdownComponents: Components = {
  table({ children }) {
    return (
      <div className="chat-table-scroll" tabIndex={0}>
        <table>{children}</table>
      </div>
    );
  },
  a({ children, href }) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  },
};

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
        skipHtml
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function ChatMessageList({
  messages,
  pendingUser,
  streamingContent,
  responsePhase,
  streamingComplete,
  streamingTools,
  streamingSuggestions,
  suggestionsLoading,
  suggestionsDisabled,
  error,
  onOpenDivination,
  onSelectSuggestion,
}: {
  messages: ChatMessage[];
  pendingUser: string | null;
  streamingContent: string;
  responsePhase: "connecting" | "thinking" | "slow" | "working" | "answering" | "stopping" | null;
  streamingComplete: boolean;
  streamingTools: StreamingToolState[];
  streamingSuggestions: string[];
  suggestionsLoading: boolean;
  suggestionsDisabled: boolean;
  error: string;
  onOpenDivination: (id: string) => void;
  onSelectSuggestion: (question: string) => void;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [
    messages,
    pendingUser,
    streamingContent,
    streamingTools,
    streamingSuggestions,
  ]);

  return (
    <div className="chat-message-scroll">
      <div className="chat-message-list" aria-live="polite">
        {messages.map((message) => {
          if (message.message_type === "tool_call") return null;
          if (message.message_type === "tool_result") {
            return (
              <ChatToolCard
                key={message.id}
                message={message}
                onOpenDivination={onOpenDivination}
              />
            );
          }
          if (message.message_type === "suggestions") {
            return (
              <SuggestedQuestions
                key={message.id}
                questions={suggestionQuestions(message)}
                disabled={suggestionsDisabled}
                onSelect={onSelectSuggestion}
              />
            );
          }
          if (
            message.message_type !== "text" ||
            !message.content ||
            message.role === "system"
          ) {
            return null;
          }
          return (
            <article
              className={`chat-message ${message.role} ${message.status}`}
              key={message.id}
            >
              <div>
                {message.role === "assistant" ? (
                  <MarkdownMessage content={message.content} />
                ) : (
                  <p>{message.content}</p>
                )}
                {message.status !== "completed" && (
                  <small>
                    {message.status === "cancelled"
                      ? "本次生成已停止"
                      : "本次回答未完整生成"}
                  </small>
                )}
              </div>
            </article>
          );
        })}

        {pendingUser && (
          <article className="chat-message user pending">
            <div><p>{pendingUser}</p></div>
          </article>
        )}

        {responsePhase &&
          !streamingContent &&
          !streamingTools.some((tool) => tool.status === "running") && (
          <div className={`chat-response-status ${responsePhase}`} role="status">
            <span className="chat-response-dots" aria-hidden="true">
              <i /><i /><i />
            </span>
            <span>
              {responsePhase === "connecting" && "正在连接问易助手…"}
              {responsePhase === "thinking" && "正在理解你的问题…"}
              {responsePhase === "slow" && "模型响应较慢，仍在耐心等待…"}
              {responsePhase === "working" && "正在处理所需信息…"}
              {responsePhase === "answering" && "正在组织回答…"}
              {responsePhase === "stopping" && "正在停止本次回答…"}
            </span>
          </div>
        )}

        {streamingTools.map((tool) => (
          <ChatToolCard
            key={tool.id}
            state={tool}
            onOpenDivination={onOpenDivination}
          />
        ))}

        {streamingContent && (
          <article className="chat-message assistant streaming">
            <div>
              <MarkdownMessage content={streamingContent} />
              {!streamingComplete && (
                <i className="chat-caret" aria-label="正在生成" />
              )}
            </div>
          </article>
        )}

        {streamingSuggestions.length > 0 && (
          <SuggestedQuestions
            questions={streamingSuggestions}
            disabled={suggestionsDisabled}
            onSelect={onSelectSuggestion}
          />
        )}

        {suggestionsLoading && (
          <div className="chat-suggestions-loading" role="status">
            <i />
            正在整理可继续追问的问题…
          </div>
        )}

        {error && (
          <div className="chat-inline-error" role="alert">
            <strong>本次问答未能完成</strong>
            <span>{error}</span>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
