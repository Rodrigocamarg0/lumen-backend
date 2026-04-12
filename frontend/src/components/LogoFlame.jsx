/**
 * LogoFlame — animated candle-flame logo mark.
 *
 * Three layered SVG paths animate independently so the flame
 * looks alive: outer body sways, mid-layer pulses, bright core
 * flickers on a shorter cycle.  A soft radial glow sits beneath.
 */
export default function LogoFlame({ className = "w-6 h-6" }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      style={{ overflow: "visible" }}
      aria-hidden
    >
      <defs>
        {/* Warm glow blur */}
        <filter
          id="lf-glow"
          x="-60%"
          y="-60%"
          width="220%"
          height="220%"
          colorInterpolationFilters="sRGB"
        >
          <feGaussianBlur stdDeviation="1.4" in="SourceGraphic" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Outer flame: dark orange → crimson */}
        <radialGradient id="lf-outer" cx="50%" cy="65%" r="55%">
          <stop offset="0%" stopColor="#fb923c" />
          <stop offset="70%" stopColor="#ea580c" />
          <stop offset="100%" stopColor="#991b1b" stopOpacity="0.7" />
        </radialGradient>

        {/* Mid flame: bright amber → orange */}
        <radialGradient id="lf-mid" cx="50%" cy="60%" r="50%">
          <stop offset="0%" stopColor="#fef08a" />
          <stop offset="55%" stopColor="#fb923c" />
          <stop offset="100%" stopColor="#ea580c" stopOpacity="0.8" />
        </radialGradient>

        {/* Core: white → pale yellow */}
        <radialGradient id="lf-core" cx="50%" cy="55%" r="50%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="60%" stopColor="#fef9c3" />
          <stop offset="100%" stopColor="#fde68a" stopOpacity="0.6" />
        </radialGradient>

        {/* Ambient halo at base */}
        <radialGradient id="lf-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fb923c" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* ── Halo glow beneath the flame ── */}
      <ellipse
        cx="12"
        cy="21.5"
        rx="8"
        ry="3"
        fill="url(#lf-halo)"
        className="lf-halo"
      />

      {/* ── Outer flame body — slow sway ── */}
      <path
        d="M12 2C10 6 8 8 8 11C8 13 9 15 10 16
           C9 16 8 15 7 14
           C6 18 8 21 12 22
           C16 21 18 18 17 14
           C16 15 15 16 14 16
           C15 15 16 13 16 11
           C16 8 14 6 12 2Z"
        fill="url(#lf-outer)"
        filter="url(#lf-glow)"
        style={{ transformBox: "fill-box", transformOrigin: "center bottom" }}
        className="lf-outer"
      />

      {/* ── Mid flame — slightly faster, reverse phase ── */}
      <path
        d="M12 4.5C11 7.5 9.5 9.5 9.5 12
           C9.5 14 10.5 15.5 11 16.5
           C10.5 15.5 10 14.5 10 13
           C9.5 15.5 10.5 18.5 12 20
           C13.5 18.5 14.5 15.5 14 13
           C14 14.5 13.5 15.5 13 16.5
           C13.5 15.5 14.5 14 14.5 12
           C14.5 9.5 13 7.5 12 4.5Z"
        fill="url(#lf-mid)"
        style={{ transformBox: "fill-box", transformOrigin: "center bottom" }}
        className="lf-mid"
      />

      {/* ── Bright core — quick flicker ── */}
      <path
        d="M12 7C11.3 9 10.5 10.5 10.5 12.5
           C10.5 14.5 11.2 16 12 18
           C12.8 16 13.5 14.5 13.5 12.5
           C13.5 10.5 12.7 9 12 7Z"
        fill="url(#lf-core)"
        style={{ transformBox: "fill-box", transformOrigin: "center bottom" }}
        className="lf-core"
      />
    </svg>
  );
}
