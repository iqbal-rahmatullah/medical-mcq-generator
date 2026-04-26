import type { ReactNode } from "react";

type FormFieldProps = {
  label: string;
  helper?: string;
  children: ReactNode;
};

export default function FormField({ label, helper, children }: FormFieldProps) {
  return (
    <label className="form-field">
      <span className="form-label">{label}</span>
      {children}
      {helper ? <span className="form-helper">{helper}</span> : null}
    </label>
  );
}
