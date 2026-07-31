"use client";

export function SuggestedQuestions({
  questions,
  disabled,
  onSelect,
}: {
  questions: string[];
  disabled: boolean;
  onSelect: (question: string) => void;
}) {
  if (questions.length === 0) return null;

  return (
    <section className="chat-suggestions" aria-label="推荐追问">
      <small>可以继续问</small>
      <div>
        {questions.map((question) => (
          <button
            type="button"
            key={question}
            disabled={disabled}
            onClick={() => onSelect(question)}
          >
            <span>{question}</span>
            <i aria-hidden="true">→</i>
          </button>
        ))}
      </div>
    </section>
  );
}

