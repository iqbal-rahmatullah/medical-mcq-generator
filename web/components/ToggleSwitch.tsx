import type { ReactNode } from "react";

type ToggleSwitchProps = {
  label: ReactNode;
  defaultChecked?: boolean;
};

export default function ToggleSwitch({ label, defaultChecked }: ToggleSwitchProps) {
  return (
    <label className="toggle">
      <input type="checkbox" defaultChecked={defaultChecked} />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-thumb" />
      </span>
      <span className="toggle-label">{label}</span>
    </label>
  );
}
