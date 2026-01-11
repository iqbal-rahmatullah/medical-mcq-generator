import type { ChangeEvent, ReactNode } from "react";

type ToggleSwitchProps = {
  label: ReactNode;
  defaultChecked?: boolean;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
};

export default function ToggleSwitch({
  label,
  defaultChecked,
  checked,
  onChange
}: ToggleSwitchProps) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    if (onChange) {
      onChange(event.target.checked);
    }
  };

  const inputProps =
    typeof checked === "boolean"
      ? { checked, onChange: handleChange }
      : { defaultChecked, onChange: handleChange };

  return (
    <label className="toggle">
      <input type="checkbox" {...inputProps} />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-thumb" />
      </span>
      <span className="toggle-label">{label}</span>
    </label>
  );
}
