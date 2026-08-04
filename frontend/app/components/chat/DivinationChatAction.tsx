"use client";

import { useEffect, useRef, useState } from "react";

export function DivinationChatAction({
  relatedCount,
  busy,
  onContinue,
  onCreateNew,
  onViewRelated,
}: {
  relatedCount: number | null;
  busy: boolean;
  onContinue: () => void;
  onCreateNew: () => void;
  onViewRelated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const hasRelatedSession = (relatedCount ?? 0) > 0;

  useEffect(() => {
    if (!open) return;

    function closeOnOutsidePointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function choose(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <div className="divination-chat-action" ref={rootRef}>
      <div className="divination-chat-split">
        <button
          type="button"
          className="divination-chat-main"
          onClick={onContinue}
          disabled={busy}
        >
          <span>问</span>
          {busy
            ? "正在打开…"
            : hasRelatedSession
              ? "继续问易"
              : "开始问易"}
        </button>
        {hasRelatedSession && (
          <button
            type="button"
            className="divination-chat-more"
            aria-label="展开问易会话操作"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
            disabled={busy}
          >
            ▾
          </button>
        )}
      </div>

      {open && (
        <>
          <button
            type="button"
            className="divination-chat-backdrop"
            aria-label="关闭问易操作"
            onClick={() => setOpen(false)}
          />
          <div className="divination-chat-menu" role="menu">
            <header>
              <span>当前卦例</span>
              <strong>问易会话</strong>
              <small>已有 {relatedCount} 段相关讨论</small>
            </header>
            <button
              type="button"
              role="menuitem"
              onClick={() => choose(onContinue)}
            >
              <b>继续最近会话</b>
              <small>保留上一次对话的完整上下文</small>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => choose(onCreateNew)}
            >
              <b>＋ 基于此卦新开讨论</b>
              <small>沿用当前排盘，但不继承聊天上下文</small>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => choose(onViewRelated)}
            >
              <b>查看相关会话（{relatedCount}）</b>
              <small>打开问易簿并定位最近一段讨论</small>
            </button>
            <button
              type="button"
              className="divination-chat-cancel"
              onClick={() => setOpen(false)}
            >
              取消
            </button>
          </div>
        </>
      )}
    </div>
  );
}
