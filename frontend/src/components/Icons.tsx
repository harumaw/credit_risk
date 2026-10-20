// Линейные иконки (stroke), цвет — через currentColor или проп color.

import type { ReactNode } from "react";

interface IconProps {
  size?: number;
  color?: string;
  strokeWidth?: number;
}

function Svg({ size = 24, color = "currentColor", strokeWidth = 2, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const HomeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 19V9l8-5 8 5v10" />
    <path d="M9 19v-6h6v6" />
  </Svg>
);

export const ChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
);

export const ClockIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 3" />
  </Svg>
);

export const TrendIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 17l5-5 4 4 8-8" />
    <path d="M14 8h6v6" />
  </Svg>
);

export const CalculatorIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M8 7h8M8 11h2M12 11h2M8 15h2M12 15h2M8 18h2M12 18h2" />
  </Svg>
);
