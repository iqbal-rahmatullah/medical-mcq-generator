type QuestionOption = {
  key: "A" | "B" | "C" | "D";
  text: string;
};

type EvidenceBlock = {
  label: string;
  source: string;
};

type QuestionStatus = "OK" | "INSUFFICIENT_EVIDENCE" | "FAILED_VERIFICATION";

type QuestionCardProps = {
  index: number;
  topic?: string;
  competency?: string;
  prompt: string;
  options: QuestionOption[];
  selectedKey?: QuestionOption["key"];
  evidence?: EvidenceBlock;
  status?: QuestionStatus;
};

export default function QuestionCard({
  index,
  topic,
  competency,
  prompt,
  options,
  selectedKey,
  evidence,
  status
}: QuestionCardProps) {
  const showStatus = status && status !== "OK";
  const showMeta = Boolean(topic || competency);

  return (
    <article className="question-card">
      <header className="question-header">
        <span className="question-badge">Q{index}.</span>
        <div className="question-body">
          <p className="question-text">
            {prompt || "Question text unavailable."}
          </p>
          {showMeta ? (
            <p className="question-meta">
              {[topic, competency].filter(Boolean).join(" · ")}
            </p>
          ) : null}
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
          </li>
        ))}
      </ul>

      {evidence ? (
        <div className="evidence-card">
          <p className="evidence-title">{evidence.label}</p>
          <p className="evidence-text">{evidence.source}</p>
        </div>
      ) : null}
    </article>
  );
}
