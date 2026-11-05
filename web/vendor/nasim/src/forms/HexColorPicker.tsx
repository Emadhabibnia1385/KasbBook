'use client';

import {
  ColorArea,
  ColorPicker,
  ColorSlider,
  ColorSwatch,
  ColorSwatchPicker,
  Label,
  parseColor,
} from '@heroui/react';

const HEX = /^#[\da-f]{6}$/i;

type HexColorPickerProps = {
  /** `#rrggbb`; anything else opens the picker on `fallback`. */
  value: string;
  onChange: (hex: string) => void;
  /** Names the swatch button and the colour area («انتخاب رنگ برند»). */
  label: string;
  /** Names the hue slider. */
  hueLabel: string;
  /** Names the row of ready-made colours. */
  presetsLabel: string;
  /** Ready-made colours; any other can still be picked. */
  presets: readonly string[];
  /** The colour the picker opens on when `value` is not one. */
  fallback: string;
};

function parse(hex: string, fallback: string) {
  try {
    return parseColor(HEX.test(hex.trim()) ? hex.trim() : fallback);
  } catch {
    return parseColor(fallback);
  }
}

// A swatch button that opens a colour picker (area, hue slider, presets) and reports an upper-case #RRGGBB.
export function HexColorPicker({
  value,
  onChange,
  label,
  hueLabel,
  presetsLabel,
  presets,
  fallback,
}: HexColorPickerProps) {
  const color = parse(value, fallback);
  const report = (next: { toString: (format: 'hex') => string }) =>
    onChange(next.toString('hex').toUpperCase());
  return (
    <ColorPicker value={color} onChange={report}>
      <ColorPicker.Trigger aria-label={label}>
        <ColorSwatch size="lg" />
      </ColorPicker.Trigger>
      <ColorPicker.Popover className="flex flex-col gap-3">
        <ColorArea
          aria-label={label}
          className="max-w-full"
          colorSpace="hsb"
          xChannel="saturation"
          yChannel="brightness"
        >
          <ColorArea.Thumb />
        </ColorArea>
        <ColorSlider channel="hue" className="gap-1 px-1" colorSpace="hsb">
          <Label>{hueLabel}</Label>
          <ColorSlider.Track>
            <ColorSlider.Thumb />
          </ColorSlider.Track>
        </ColorSlider>
        <ColorSwatchPicker
          aria-label={presetsLabel}
          value={color}
          onChange={report}
        >
          {presets.map((hex) => (
            <ColorSwatchPicker.Item key={hex} color={hex}>
              <ColorSwatchPicker.Swatch />
            </ColorSwatchPicker.Item>
          ))}
        </ColorSwatchPicker>
      </ColorPicker.Popover>
    </ColorPicker>
  );
}
