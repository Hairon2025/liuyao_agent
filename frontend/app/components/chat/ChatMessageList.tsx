"use client";

import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../types";
import {
  ChatToolCard,
  type StreamingToolState,
} from "./ChatToolCard";

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function ChatMessageList({
  messages,
  pendingUser,
  streamingContent,
  streamingTools,
  error,
  onOpenDivination,
}: {
  messages: ChatMessage[];
  pendingUser: string | null;
  streamingContent: string;
  streamingTools: StreamingToolState[];
  error: string;
  onOpenDivination: (id: string) => void;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, pendingUser, streamingContent, streamingTools]);

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
              <span>{message.role === "user" ? "问" : "易"}</span>
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
            <span>问</span>
            <div><p>{pendingUser}</p></div>
          </article>
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
            <span>易</span>
            <div>
              <MarkdownMessage content={streamingContent} />
              <i className="chat-caret" aria-label="正在生成" />
            </div>
          </article>
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
