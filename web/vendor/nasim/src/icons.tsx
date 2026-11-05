import type { ComponentProps } from 'react';

// The six Solar icons (linear set, 480 Design, CC BY 4.0) Nasim draws, inline so that no bundler
// plugin and no icon font is needed. Decorative: the control around an icon carries the name.
type IconProps = ComponentProps<'svg'>;

function Svg(props: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="1.2em"
      height="1.2em"
      fill="none"
      aria-hidden="true"
      focusable="false"
      {...props}
    />
  );
}

export function BackIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="m15 5l-6 7l6 7"
      />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g stroke="currentColor" strokeWidth={1.5}>
        <circle cx={12} cy={12} r={10} />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m8.5 12.5l2 2l5-5"
        />
      </g>
    </Svg>
  );
}

export function CopyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g stroke="currentColor" strokeWidth={1.5}>
        <path d="M6 11c0-2.828 0-4.243.879-5.121C7.757 5 9.172 5 12 5h3c2.828 0 4.243 0 5.121.879C21 6.757 21 8.172 21 11v5c0 2.828 0 4.243-.879 5.121C19.243 22 17.828 22 15 22h-3c-2.828 0-4.243 0-5.121-.879C6 20.243 6 18.828 6 16z" />
        <path d="M6 19a3 3 0 0 1-3-3v-6c0-3.771 0-5.657 1.172-6.828S7.229 2 11 2h4a3 3 0 0 1 3 3" />
      </g>
    </Svg>
  );
}

export function EmptyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth={1.5}
        d="m15.578 3.382l2 1.05c2.151 1.129 3.227 1.693 3.825 2.708C22 8.154 22 9.417 22 11.942v.117c0 2.524 0 3.787-.597 4.801c-.598 1.015-1.674 1.58-3.825 2.709l-2 1.049C13.822 21.539 12.944 22 12 22s-1.822-.46-3.578-1.382l-2-1.05c-2.151-1.129-3.227-1.693-3.825-2.708C2 15.846 2 14.583 2 12.06v-.117c0-2.525 0-3.788.597-4.802c.598-1.015 1.674-1.58 3.825-2.708l2-1.05C10.178 2.461 11.056 2 12 2s1.822.46 3.578 1.382ZM21 7.5L12 12m0 0L3 7.5m9 4.5v9.5"
      />
    </Svg>
  );
}

export function ErrorIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeWidth={1.5}
        d="M5.312 10.762C8.23 5.587 9.689 3 12 3s3.77 2.587 6.688 7.762l.364.644c2.425 4.3 3.638 6.45 2.542 8.022S17.786 21 12.364 21h-.728c-5.422 0-8.134 0-9.23-1.572s.117-3.722 2.542-8.022z"
      />
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth={1.5}
        d="M12 8v5"
      />
      <circle cx={12} cy={16} r={1} fill="currentColor" />
    </Svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M12 20V4m0 0l6 6m-6-6l-6 6"
      />
    </Svg>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g stroke="currentColor" strokeLinecap="round" strokeWidth={1.5}>
        <circle cx={12} cy={12} r={4} />
        <path d="M12 2.5v2M12 19.5v2M4.7 4.7l1.4 1.4M17.9 17.9l1.4 1.4M2.5 12h2M19.5 12h2M4.7 19.3l1.4-1.4M17.9 6.1l1.4-1.4" />
      </g>
    </Svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"
      />
    </Svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g stroke="currentColor" strokeLinecap="round" strokeWidth={1.5}>
        <circle cx={12} cy={12} r={10} />
        <path d="M12 11v5" />
      </g>
      <circle cx={12} cy={8} r={1} fill="currentColor" />
    </Svg>
  );
}

export function DangerIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M8 3h8l5 5v8l-5 5H8l-5-5V8zM9.5 9.5l5 5M14.5 9.5l-5 5"
      />
    </Svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="m6 9l6 6l6-6"
      />
    </Svg>
  );
}

export function OfflineIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M2 8.8a15 15 0 0 1 4.2-2.6M22 8.8a15 15 0 0 0-8.6-3.7M5 12.9a10 10 0 0 1 5-2.7M19 12.9a10 10 0 0 0-2.4-1.9M8.5 16.4a5 5 0 0 1 7 0M12 20h.01M2 2l20 20"
      />
    </Svg>
  );
}

export function MenuIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth={1.5}
        d="M4 6h16M4 12h16M4 18h16"
      />
    </Svg>
  );
}

export function NeutralIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g stroke="currentColor" strokeLinecap="round" strokeWidth={1.5}>
        <circle cx={12} cy={12} r={10} />
        <path d="M8 12h8" />
      </g>
    </Svg>
  );
}

// Six dots, drawn here (not from the Solar set): the grip that says a row can be dragged.
export function GripIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <g fill="currentColor">
        <circle cx={9} cy={6} r={1.5} />
        <circle cx={15} cy={6} r={1.5} />
        <circle cx={9} cy={12} r={1.5} />
        <circle cx={15} cy={12} r={1.5} />
        <circle cx={9} cy={18} r={1.5} />
        <circle cx={15} cy={18} r={1.5} />
      </g>
    </Svg>
  );
}
