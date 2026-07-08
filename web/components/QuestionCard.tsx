type QuestionOption = {
  key: "A" | "B" | "C" | "D";
  text: string;
};

type EvidenceBlock = {
  label: string;
  items: Array<{
    docId: string;
    source: string;
    span: string;
  }>;
};

type QuestionStatus = "OK" | "INSUFFICIENT_EVIDENCE" | "FAILED_VERIFICATION";

type QuestionCardProps = {
  index: number;
  prompt: string;
  options: QuestionOption[];
  selectedKey?: QuestionOption["key"];
  explanation?: string;
  evidence?: EvidenceBlock;
  status?: QuestionStatus;
};

export default function QuestionCard({
  index,
  prompt,
  options,
  selectedKey,
  explanation,
  evidence,
  status
}: QuestionCardProps) {
  const showStatus = status && status !== "OK";
  const showExplanation = Boolean(selectedKey && explanation);

  return (
    <article className="question-card">
      <header className="question-header">
        <span className="question-badge">Q{index}.</span>
        <div className="question-body">
          <p className="question-text">
            {prompt || "Question text unavailable."}
          </p>
        </div>
        {showStatus ? (
          <span className={`status-chip ${status?.toLowerCase()}`}>{status}</span>
        ) : null}
      </header>

      <ul className="option-list">
        {options.map((option) => (
          <li
            key={option.key}
            className={`option-row${option.key === selectedKey ? " selected" : ""}`}
          >
            <span className="option-indicator" aria-hidden="true" />
            <span className="option-label">
              <strong>{option.key}.</strong> {option.text}
            </span>
            {showExplanation && option.key === selectedKey ? (
              <details className="explanation-panel">
                <summary className="explanation-summary">Explanation</summary>
                <p className="explanation-text">{explanation}</p>
              </details>
            ) : null}
          </li>
        ))}
      </ul>

      {evidence ? (
        <div className="evidence-card">
          <p className="evidence-title">{evidence.label}</p>
          <ul className="evidence-list">
            {evidence.items.map((item, itemIndex) => (
              <li key={`${item.docId}-${itemIndex}`} className="evidence-item">
                <div className="evidence-meta">
                  <span className="evidence-source">{item.source}</span>
                  <span className="evidence-doc">{item.docId}</span>
                </div>
                {item.span ? (
                  <p className="evidence-text">{item.span}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}
