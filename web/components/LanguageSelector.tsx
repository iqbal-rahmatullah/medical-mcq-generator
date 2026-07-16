"use client"

type LanguageSelectorProps = {
  value: "en" | "id"
  onChange: (lang: "en" | "id") => void
  name: string
}

const LANGUAGES: { code: "en" | "id"; flag: string; label: string }[] = [
  { code: "en", flag: "🇬🇧", label: "EN" },
  { code: "id", flag: "🇮🇩", label: "ID" },
]

export default function LanguageSelector({
  value,
  onChange,
  name,
}: LanguageSelectorProps) {
  return (
    <div className='language-selector' role='group' aria-label='Display language'>
      {LANGUAGES.map((lang) => (
        <label
          key={lang.code}
          className={`lang-radio-label${value === lang.code ? " active" : ""}`}
        >
          <input
            type='radio'
            name={name}
            value={lang.code}
            checked={value === lang.code}
            onChange={() => onChange(lang.code)}
            className='lang-radio-input'
          />
          {lang.flag} {lang.label}
        </label>
      ))}
    </div>
  )
}
