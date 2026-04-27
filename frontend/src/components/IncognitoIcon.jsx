export default function IncognitoIcon({ className = "w-5 h-5" }) {
  return (
    <svg
      className={className}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 13l1.5-6a2 2 0 011.94-1.5h11.12A2 2 0 0119.5 7L21 13"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M3 13h18"
      />
      <circle cx="7.5" cy="16.5" r="2.5" strokeWidth={2} />
      <circle cx="16.5" cy="16.5" r="2.5" strokeWidth={2} />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 16.5h4"
      />
    </svg>
  );
}
