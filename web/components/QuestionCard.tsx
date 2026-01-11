type QuestionOption = {
  key: "A" | "B" | "C" | "D";
  text: string;
};

type EvidenceBlock = {
  label: string;
  source: string;
};

type QuestionCardProps = {
  index: number;
  prompt: string;
  options: QuestionOption[];
  selectedKey?: QuestionOption["key"];
  evidence?: EvidenceBlock;
};

export default function QuestionCard({
  index,
  prompt,
  options,
  selectedKey,
  evidence
}: QuestionCardProps) {
  return (
    <article className="question-card">
      <header className="question-header">
        <span className="question-badge">Q{index}.</span>
        <p className="question-text">{prompt}</p>
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
          <p className="evidence-text">
            {evidence.source}
          </p>
        </div>
      ) : null}
    </article>
  );
}
