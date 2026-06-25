import React from "react";

type IconName = "activity" | "download" | "film" | "gauge" | "heart-pulse" | "upload";

interface IconProps {
  name: IconName;
  size?: number;
  "aria-hidden"?: "true";
}

const paths: Record<IconName, React.ReactNode> = {
  activity: <polyline points="3 12 7 12 10 4 14 20 17 12 21 12" />,
  download: (
    <>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </>
  ),
  film: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="M8 3v18" />
      <path d="M16 3v18" />
      <path d="M4 8h4" />
      <path d="M16 8h4" />
      <path d="M4 16h4" />
      <path d="M16 16h4" />
    </>
  ),
  gauge: (
    <>
      <path d="M4 14a8 8 0 0 1 16 0" />
      <path d="M12 14l4-4" />
      <path d="M6 20h12" />
    </>
  ),
  "heart-pulse": (
    <>
      <path d="M20 7.5c0 5-8 10.5-8 10.5S4 12.5 4 7.5A4.2 4.2 0 0 1 12 5a4.2 4.2 0 0 1 8 2.5Z" />
      <path d="M3 12h4l2-3 3 6 2-3h7" />
    </>
  ),
  upload: (
    <>
      <path d="M12 21V9" />
      <path d="m7 14 5-5 5 5" />
      <path d="M5 3h14" />
    </>
  ),
};

export function Icon({ name, size = 18, "aria-hidden": ariaHidden }: IconProps): React.ReactElement {
  return (
    <svg
      aria-hidden={ariaHidden}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}
