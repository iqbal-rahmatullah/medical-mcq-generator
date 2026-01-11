import type { CSSProperties } from "react";

type AvatarProps = {
  name: string;
  color?: string;
};

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return "?";
  }
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export default function Avatar({ name, color = "#0f5fd6" }: AvatarProps) {
  const style: CSSProperties = {
    background: color
  };

  return (
    <div className="avatar" style={style} title={name}>
      <span>{getInitials(name)}</span>
      <span className="avatar-dot" />
    </div>
  );
}
