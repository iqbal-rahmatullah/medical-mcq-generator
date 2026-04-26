import Link from "next/link";

type NavLinkProps = {
  href: string;
  label: string;
  active?: boolean;
};

export default function NavLink({ href, label, active = false }: NavLinkProps) {
  return (
    <Link className={`nav-link${active ? " active" : ""}`} href={href}>
      {label}
    </Link>
  );
}
