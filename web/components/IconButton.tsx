import type { ReactNode } from "react";

type IconButtonProps = {
  ariaLabel: string;
  children: ReactNode;
};

export default function IconButton({ ariaLabel, children }: IconButtonProps) {
  return (
    <button type="button" className="icon-button" aria-label={ariaLabel}>
      {children}
    </button>
  );
}
